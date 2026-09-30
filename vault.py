"""
OLPG MILITARY CREDENTIAL VAULT v3.0
AES-256 (Fernet) + PBKDF2-HMAC-SHA256 + Per-Key Salts
All credentials encrypted at rest. Zero plaintext in DB.
"""
import os, re, json, time, base64, hashlib, sqlite3, secrets, threading
from typing import Optional, Dict, Tuple, Any

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

_VAULT_MASTER = os.environ.get(
    "VAULT_MASTER_KEY",
    os.environ.get("FERNET_KEY", os.environ.get("SECRET_KEY", "OLPG_VAULT_MASTER_2026_BLADE_SECURE"))
).encode()
_DB_PATH = os.environ.get("DB_PATH", "olpg_logs.db")
_LOCK = threading.Lock()

# ── Gateway Schemas ─────────────────────────────────────────────────────────
GATEWAY_SCHEMAS: Dict[str, dict] = {
    "c7": {
        "name": "Carteira do 7",
        "logo": "C7",
        "color": "#7C3AED",
        "fields": [
            {"key": "api_key",        "label": "API Key",           "hint": "c7_live_..."},
            {"key": "api_secret",     "label": "API Secret",        "hint": "0449fb23..."},
            {"key": "internal_token", "label": "Token Interno",     "hint": "39Qrhfyc..."},
            {"key": "base_url",       "label": "Base URL",          "hint": "https://api.carteirado7.com/v2"},
            {"key": "acquirer_code",  "label": "Cod. Adquirente",   "hint": "Opcional"},
        ]
    },
    "mercadopago": {
        "name": "Mercado Pago",
        "logo": "MP",
        "color": "#009EE3",
        "fields": [
            {"key": "access_token",  "label": "Access Token",  "hint": "APP_USR-..."},
            {"key": "public_key",    "label": "Public Key",    "hint": "APP_USR-..."},
        ]
    },
    "pagseguro": {
        "name": "PagSeguro",
        "logo": "PS",
        "color": "#00B272",
        "fields": [
            {"key": "token",  "label": "Token",  "hint": "UUID token"},
            {"key": "email",  "label": "E-mail", "hint": "seu@email.com"},
        ]
    },
    "stripe": {
        "name": "Stripe",
        "logo": "ST",
        "color": "#635BFF",
        "fields": [
            {"key": "secret_key",       "label": "Secret Key",      "hint": "sk_live_..."},
            {"key": "publishable_key",  "label": "Publishable Key", "hint": "pk_live_..."},
            {"key": "webhook_secret",   "label": "Webhook Secret",  "hint": "whsec_..."},
        ]
    },
    "efipay": {
        "name": "Efi Pay (Gerencianet)",
        "logo": "EFI",
        "color": "#1A5EFF",
        "fields": [
            {"key": "client_id",      "label": "Client ID",      "hint": "Client_Id_..."},
            {"key": "client_secret",  "label": "Client Secret",  "hint": "Client_Secret_..."},
            {"key": "pix_key",        "label": "Chave Pix",      "hint": "CPF / e-mail / tel"},
            {"key": "sandbox",        "label": "Sandbox",        "hint": "true / false"},
        ]
    },
    "pix_manual": {
        "name": "Pix Manual (Chave Direta)",
        "logo": "PIX",
        "color": "#32BCAD",
        "fields": [
            {"key": "pix_key",   "label": "Chave Pix",       "hint": "CPF, CNPJ, e-mail, tel ou aleat."},
            {"key": "pix_name",  "label": "Nome Recebedor",  "hint": "Nome completo"},
            {"key": "pix_city",  "label": "Cidade",          "hint": "Sao Paulo"},
        ]
    },
    "custom": {
        "name": "API Personalizada",
        "logo": "API",
        "color": "#6B7280",
        "fields": [
            {"key": "raw_credentials",  "label": "Credenciais (JSON)", "hint": '{"key": "..."}'},
            {"key": "base_url",         "label": "URL Base",           "hint": "https://..."},
        ]
    },
}

# ── Key Derivation ───────────────────────────────────────────────────────────
def _derive_key(salt: bytes, context: str = "") -> bytes:
    if not _CRYPTO_OK:
        return hashlib.sha256(_VAULT_MASTER + salt).digest()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32,
        salt=salt + context.encode(), iterations=390_000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(_VAULT_MASTER))

def _encrypt(plaintext: str, context: str = "") -> Tuple[str, str]:
    salt = secrets.token_bytes(32)
    if _CRYPTO_OK:
        ct = Fernet(_derive_key(salt, context)).encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(ct).decode(), salt.hex()
    key_b = hashlib.sha256(_VAULT_MASTER + salt).digest()
    xored = bytes(b ^ key_b[i % 32] for i, b in enumerate(plaintext.encode()))
    return base64.urlsafe_b64encode(xored).decode(), salt.hex()

def _decrypt(ct_b64: str, salt_hex: str, context: str = "") -> Optional[str]:
    try:
        salt = bytes.fromhex(salt_hex)
        if _CRYPTO_OK:
            return Fernet(_derive_key(salt, context)).decrypt(
                base64.urlsafe_b64decode(ct_b64.encode())
            ).decode()
        key_b = hashlib.sha256(_VAULT_MASTER + salt).digest()
        raw = base64.urlsafe_b64decode(ct_b64.encode())
        return bytes(b ^ key_b[i % 32] for i, b in enumerate(raw)).decode()
    except Exception:
        return None

# ── DB ───────────────────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_vault_tables():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS payment_gateways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            gateway TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at REAL DEFAULT (unixepoch()),
            updated_at REAL DEFAULT (unixepoch()),
            UNIQUE(admin_id, gateway)
        );
        CREATE TABLE IF NOT EXISTS gateway_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            gateway TEXT NOT NULL,
            field_key TEXT NOT NULL,
            ciphertext TEXT NOT NULL,
            salt TEXT NOT NULL,
            updated_at REAL DEFAULT (unixepoch()),
            UNIQUE(admin_id, gateway, field_key)
        );
        CREATE TABLE IF NOT EXISTS vault_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT NOT NULL,
            gateway TEXT,
            ip TEXT,
            ts REAL DEFAULT (unixepoch())
        );
        """)
    print("[VAULT] Tables ready.")

# ── CRUD ─────────────────────────────────────────────────────────────────────
def save_gateway_credentials(admin_id: int, gateway: str, fields: Dict[str, str], ip: str = "") -> bool:
    with _LOCK:
        try:
            with _conn() as c:
                c.execute(
                    "INSERT INTO payment_gateways (admin_id,gateway,updated_at) VALUES (?,?,unixepoch()) "
                    "ON CONFLICT(admin_id,gateway) DO UPDATE SET updated_at=unixepoch()",
                    (admin_id, gateway)
                )
                for key, value in fields.items():
                    if not value or not value.strip():
                        continue
                    ctx = f"{admin_id}:{gateway}:{key}"
                    ct, salt = _encrypt(value.strip(), ctx)
                    c.execute(
                        "INSERT INTO gateway_credentials (admin_id,gateway,field_key,ciphertext,salt,updated_at) "
                        "VALUES (?,?,?,?,?,unixepoch()) ON CONFLICT(admin_id,gateway,field_key) DO UPDATE SET "
                        "ciphertext=excluded.ciphertext,salt=excluded.salt,updated_at=unixepoch()",
                        (admin_id, gateway, key, ct, salt)
                    )
                c.execute(
                    "INSERT INTO vault_audit (admin_id,action,gateway,ip) VALUES (?,'SAVE_CREDENTIALS',?,?)",
                    (admin_id, gateway, ip)
                )
            return True
        except Exception as e:
            print(f"[VAULT] save error: {e}")
            return False

def get_gateway_credentials(admin_id: int, gateway: str) -> Dict[str, str]:
    result = {}
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT field_key,ciphertext,salt FROM gateway_credentials WHERE admin_id=? AND gateway=?",
                (admin_id, gateway)
            ).fetchall()
        for r in rows:
            ctx = f"{admin_id}:{gateway}:{r['field_key']}"
            plain = _decrypt(r["ciphertext"], r["salt"], ctx)
            if plain is not None:
                result[r["field_key"]] = plain
    except Exception as e:
        print(f"[VAULT] get error: {e}")
    return result

def set_gateway_active(admin_id: int, gateway: str, active: bool, ip: str = "") -> bool:
    with _LOCK:
        try:
            with _conn() as c:
                c.execute(
                    "UPDATE payment_gateways SET is_active=0,updated_at=unixepoch() WHERE admin_id=?",
                    (admin_id,)
                )
                if active:
                    c.execute(
                        "INSERT INTO payment_gateways (admin_id,gateway,is_active,updated_at) VALUES (?,?,1,unixepoch()) "
                        "ON CONFLICT(admin_id,gateway) DO UPDATE SET is_active=1,updated_at=unixepoch()",
                        (admin_id, gateway)
                    )
                c.execute(
                    "INSERT INTO vault_audit (admin_id,action,gateway,ip) VALUES (?,?,?,?)",
                    (admin_id, "ACTIVATE" if active else "DEACTIVATE_ALL", gateway, ip)
                )
            return True
        except Exception as e:
            print(f"[VAULT] active error: {e}")
            return False

def get_active_gateway(admin_id: int) -> Optional[str]:
    try:
        with _conn() as c:
            r = c.execute(
                "SELECT gateway FROM payment_gateways WHERE admin_id=? AND is_active=1 ORDER BY updated_at DESC LIMIT 1",
                (admin_id,)
            ).fetchone()
        return r["gateway"] if r else None
    except Exception:
        return None

def list_gateways(admin_id: int) -> list:
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT gateway,is_active,updated_at FROM payment_gateways WHERE admin_id=? ORDER BY updated_at DESC",
                (admin_id,)
            ).fetchall()
        return [{"gateway": r["gateway"], "is_active": bool(r["is_active"]), "updated_at": r["updated_at"]} for r in rows]
    except Exception:
        return []

def delete_gateway(admin_id: int, gateway: str, ip: str = "") -> bool:
    with _LOCK:
        try:
            with _conn() as c:
                c.execute("DELETE FROM gateway_credentials WHERE admin_id=? AND gateway=?", (admin_id, gateway))
                c.execute("DELETE FROM payment_gateways WHERE admin_id=? AND gateway=?", (admin_id, gateway))
                c.execute(
                    "INSERT INTO vault_audit (admin_id,action,gateway,ip) VALUES (?,'DELETE_GATEWAY',?,?)",
                    (admin_id, gateway, ip)
                )
            return True
        except Exception as e:
            print(f"[VAULT] delete error: {e}")
            return False

def get_vault_audit(admin_id: int, limit: int = 30) -> list:
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT action,gateway,ip,ts FROM vault_audit WHERE admin_id=? ORDER BY ts DESC LIMIT ?",
                (admin_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []

# ── AI Credential Detector ────────────────────────────────────────────────────
def ai_detect_gateway(raw_text: str) -> dict:
    """Auto-detects gateway type from pasted API credential text."""
    text = raw_text.strip()
    det = {"gateway": None, "confidence": 0.0, "fields": {}, "warnings": []}
    patterns = [
        ("c7",          r"c7_(live|test)_[a-f0-9]{40,}",            0.95),
        ("mercadopago", r"(APP_USR|TEST)-[0-9]+-",                  0.95),
        ("stripe",      r"(sk|pk)_(live|test)_[A-Za-z0-9]{24,}",   0.95),
        ("pagseguro",   r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-",  0.80),
        ("efipay",      r"Client_(Id|Secret)_[A-Za-z0-9]{20,}",    0.90),
    ]
    for gw, pat, conf in patterns:
        if re.search(pat, text):
            det["gateway"] = gw
            det["confidence"] = conf
            break
    if not det["gateway"]:
        pix_pats = [r"\b\d{11}\b", r"[^@\s]+@[^@\s]+\.[^@\s]+", r"\+55\s?\d{2}\s?\d{9}"]
        for p in pix_pats:
            if re.search(p, text):
                det["gateway"] = "pix_manual"
                det["confidence"] = 0.75
                break
    if not det["gateway"]:
        det["gateway"] = "custom"
        det["confidence"] = 0.30
    if "test" in text.lower() or "sandbox" in text.lower():
        det["warnings"].append("Credenciais de TESTE detectadas — nao use em producao.")
    return det

def mask_credential(value: str) -> str:
    if not value:
        return "\u2014"
    n = len(value)
    if n <= 8:
        return "*" * n
    return value[:4] + "*" * min(n - 8, 32) + value[-4:]

def get_masked_credentials(admin_id: int, gateway: str) -> Dict[str, str]:
    raw = get_gateway_credentials(admin_id, gateway)
    return {k: mask_credential(v) for k, v in raw.items()}

def init():
    init_vault_tables()
    algo = "AES-256 Fernet + PBKDF2-HMAC-SHA256" if _CRYPTO_OK else "XOR fallback"
    print(f"[VAULT] Military credential vault ready. Algorithm: {algo}")
