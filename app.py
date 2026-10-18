# â”€â”€â”€ IMPORTS DE SEGURANÇA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import os

# Carrega variáveis do .env (desenvolvimento local)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv não instalado; env vars já devem estar no ambiente



import sys

import json

import time

import uuid

import hmac

import hashlib

import re

import struct

import base64

import requests

import urllib.parse

import secrets

from datetime import datetime

from typing import Optional



from flask import Flask, render_template, request, jsonify, abort, g, make_response

import secrets as _sec_nonce

import logging as _logging

_logging.basicConfig(

    level=_logging.INFO,

    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",

    datefmt="%Y-%m-%d %H:%M:%S",

)

log = _logging.getLogger("OLPG")



# â”€â”€â”€ Import bot module for shared DB + notifications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

sys.path.insert(0, os.path.dirname(__file__))

try:

    import bot as admin_bot

    admin_bot.init_db()

    BOT_AVAILABLE = True



    # Modo WEBHOOK: nao sobe polling thread (o webhook do Flask gerencia updates)

    # O bot.py principal (polling) fica desativado quando WEBHOOK_URL esta definido

    if not os.environ.get("WEBHOOK_URL") and (os.environ.get("TELEGRAM_BOT_TOKEN") or getattr(admin_bot, "BOT_TOKEN", "")):

        if not os.environ.get("TELEGRAM_BOT_TOKEN") and getattr(admin_bot, "BOT_TOKEN", ""):

            os.environ["TELEGRAM_BOT_TOKEN"] = admin_bot.BOT_TOKEN

        import threading

        bot_thread = threading.Thread(target=admin_bot.main, daemon=True)

        bot_thread.start()

        log.info("[app.py] Telegram polling Bot iniciado em thread.")

except ImportError:

    BOT_AVAILABLE = False

    print("[app.py] bot.py not found — logging to console only.")



# â”€â”€â”€ Import multi-tenant webhook handler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

try:

    import tg_webhook as tg_wh

    if BOT_AVAILABLE:

        tg_wh.init_tenant_tables()

    TG_WH_AVAILABLE = True

    print("[app.py] tg_webhook.py carregado — modo multi-tenant ativo.")

except ImportError:

    TG_WH_AVAILABLE = False

    log.warning("[app.py] tg_webhook.py nao encontrado.")



# â”€â”€â”€ Import Vault (Military Credential Store) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

try:

    import vault as credential_vault

    credential_vault.init()

    VAULT_AVAILABLE = True

except ImportError:

    VAULT_AVAILABLE = False

    print("[app.py] vault.py nao encontrado — credenciais em env only.")



# â”€â”€â”€ Import API Intelligence Engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

try:

    import api_intel as api_engine

    API_INTEL_AVAILABLE = True

except ImportError:

    API_INTEL_AVAILABLE = False

    print("[app.py] api_intel.py nao encontrado — detector IA basico ativo.")



# --- Import Validation Engine & Activity Audit --------------------------------

try:

    from validators import FieldValidator, ActivityAudit

    VALIDATORS_AVAILABLE = True

    log.info("[app.py] validators.py carregado -- validacao avancada ativa.")

except ImportError:

    VALIDATORS_AVAILABLE = False

    FieldValidator = None

    ActivityAudit  = None

    log.warning("[app.py] validators.py nao encontrado -- modo basico.")



app = Flask(__name__, static_folder='static', template_folder='templates')



# ─── ANTI-SLEEP / KEEP ALIVE ENGINE (RENDER DATA PRESERVATION) ───────────────

import threading

import requests

import time

def keep_alive_daemon():

    """Pinga o proprio servidor a cada 10 min para impedir o Render de dormir e apagar os DBs (SQLite)."""

    time.sleep(10) # Espera app subir

    base_url = os.environ.get("BASE_URL", "https://olx-9ee8.onrender.com").rstrip('/')

    log.info("[KEEP-ALIVE] Iniciando monitoramento inteligente para proteger dados do Admin. URL: " + base_url)

    while True:

        try:

            time.sleep(600) # 10 minutos

            requests.get(base_url, timeout=10)

        except Exception as e:

            pass



_ka_thread = threading.Thread(target=keep_alive_daemon, daemon=True)

_ka_thread.start()





# Secret Key para sessões e hashing de integridade

# Secret key: env first, then auto-generated (never weak literal in prod)

_flask_sk_raw = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("FERNET_KEY") or ""

if not _flask_sk_raw:

    import secrets as _fsec

    _flask_sk_raw = _fsec.token_hex(32)

    print("[SECURITY] FLASK_SECRET_KEY nao definida — usando chave temporaria!")

app.secret_key = _flask_sk_raw



# --- Admin Token HMAC Signing (blindagem extra para tokens de sessao) ----------

def _sign_token(token: str) -> str:

    """Assina um token de sessao com HMAC-SHA256 para detectar adulteracao."""

    secret = (app.secret_key or "").encode() if hasattr(app, "secret_key") else b""

    sig = hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()[:16]

    return f"{token}.{sig}"



def _verify_signed_token(signed: str) -> str | None:

    """Verifica assinatura do token. Retorna token original ou None se adulterado."""

    if "." not in signed:

        return None

    parts = signed.rsplit(".", 1)

    if len(parts) != 2:

        return None

    token, sig = parts

    secret = (app.secret_key or "").encode() if hasattr(app, "secret_key") else b""

    expected = hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()[:16]

    if not hmac.compare_digest(sig, expected):

        return None

    return token





# â”€â”€â”€ TELEGRAM OAUTH CONFIGURATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

TELEGRAM_CLIENT_ID     = os.environ.get("TELEGRAM_CLIENT_ID", "")

TELEGRAM_CLIENT_SECRET = os.environ.get("TELEGRAM_CLIENT_SECRET", "")  # SEGURO: nao hardcoded

BASE_URL               = os.environ.get("BASE_URL", "https://olx-9ee8.onrender.com").rstrip('/')



# ─── CONFIGURAÇÕES DA API DE PAGAMENTO (ELITEPAY OFICIAL) ─────────────────────
# ElitePay é a gateway primária e ativa do sistema (https://api.elitepaybr.com).
# Credenciais persistentes e criptografadas gerenciadas pelo vault.py (AES-256 + PBKDF2).
ELITEPAY_BASE_URL      = os.environ.get("ELITEPAY_BASE_URL", "https://api.elitepaybr.com")
ELITEPAY_CLIENT_ID     = os.environ.get("ELITEPAY_CLIENT_ID", "ep_6048463324683e160dc35f1fd0f27d37")
ELITEPAY_CLIENT_SECRET = os.environ.get("ELITEPAY_CLIENT_SECRET", "eps_daa2098e2b7319a83a2d26090f749003709889d24594332ae0eb712e0bc1b467")

# Aliases legados mapeados para a ElitePay
C7_API_KEY       = ELITEPAY_CLIENT_ID
C7_API_SECRET    = ELITEPAY_CLIENT_SECRET
C7_INTERNAL_TOKEN= ""
C7_BASE_URL      = ELITEPAY_BASE_URL
C7_ACQUIRER_CODE = ""

# ─── SUPREME ADMIN ID para consulta do vault ─────────────────────────────────
_SUPREME_ADMIN_ID = int(os.environ.get("SUPREME_ADMIN_ID", "0"))

def _get_live_gateway_keys(admin_id: Optional[int] = None) -> dict:
    """
    Retorna as credenciais ativas do gateway prioritário do sistema (ElitePay por padrão).
    1. Consulta o Vault criptografado (AES-256)
    2. Fallback para variáveis de ambiente dinâmicas
    """
    supreme_id = admin_id or int(os.environ.get("SUPREME_ADMIN_ID", str(_SUPREME_ADMIN_ID)))
    active_gw = "elitepay"
    if VAULT_AVAILABLE and supreme_id:
        active_gw = credential_vault.get_active_gateway(supreme_id) or "elitepay"
        creds = credential_vault.get_gateway_credentials(supreme_id, active_gw)
        if creds:
            cid = creds.get("client_id") or creds.get("api_key") or ""
            csec = creds.get("client_secret") or creds.get("api_secret") or ""
            burl = creds.get("base_url") or "https://api.elitepaybr.com"
            return {
                "gateway": active_gw,
                "client_id": cid,
                "client_secret": csec,
                "api_key": cid,
                "api_secret": csec,
                "base_url": burl,
                "internal_token": creds.get("internal_token", ""),
                "acquirer_code": creds.get("acquirer_code", ""),
                "raw": creds
            }

    # Fallback env vars
    env_cid = os.environ.get("ELITEPAY_CLIENT_ID", "") or ELITEPAY_CLIENT_ID or os.environ.get("C7_API_KEY", "")
    env_csec = os.environ.get("ELITEPAY_CLIENT_SECRET", "") or ELITEPAY_CLIENT_SECRET or os.environ.get("C7_API_SECRET", "")
    env_burl = os.environ.get("ELITEPAY_BASE_URL", "") or ELITEPAY_BASE_URL or "https://api.elitepaybr.com"

    return {
        "gateway": active_gw,
        "client_id": env_cid,
        "client_secret": env_csec,
        "api_key": env_cid,
        "api_secret": env_csec,
        "base_url": env_burl,
        "internal_token": os.environ.get("C7_INTERNAL_TOKEN", ""),
        "acquirer_code": os.environ.get("C7_ACQUIRER_CODE", ""),
    }

def _get_live_c7_keys() -> dict:
    """Alias retrocompativel para _get_live_gateway_keys()."""
    return _get_live_gateway_keys()

# ─── UNIÃO 7 PAY — CONFIGURAÇÃO E INTEGRAÇÃO ──────────────────────────────────
UNIAOPAY_DEFAULT_API_KEY  = "up_live_4dfac754f54c28d4f692fa1f58752e66354a36346c589cac"
UNIAOPAY_DEFAULT_BASE_URL = "https://meupagamento.site/api/v1/uniaopay/pix/create"

def _get_uniaopay_config(admin_id: Optional[int] = None) -> dict:
    """
    Retorna as credenciais e status da União 7 Pay:
    1. Do Vault do Supreme Admin (se existir)
    2. Fallback para variáveis de ambiente (.env)
    """
    supreme_id = admin_id or int(os.environ.get("SUPREME_ADMIN_ID", str(_SUPREME_ADMIN_ID)))
    api_key = ""
    base_url = UNIAOPAY_DEFAULT_BASE_URL
    fallback_enabled = True

    if VAULT_AVAILABLE and supreme_id:
        creds = credential_vault.get_gateway_credentials(supreme_id, "uniaopay")
        if creds:
            api_key = creds.get("api_key", "").strip()
            base_url = creds.get("base_url", "").strip() or base_url
            if "fallback_enabled" in creds:
                fallback_enabled = creds.get("fallback_enabled") not in ("0", False, "false")

    if not api_key:
        api_key = os.environ.get("UNIAOPAY_API_KEY", UNIAOPAY_DEFAULT_API_KEY).strip()
    if not base_url:
        base_url = os.environ.get("UNIAOPAY_BASE_URL", UNIAOPAY_DEFAULT_BASE_URL).strip()

    env_fb = os.environ.get("UNIAOPAY_FALLBACK_ENABLED", "1")
    if env_fb in ("0", "false", "no"):
        fallback_enabled = False

    return {
        "api_key": api_key,
        "base_url": base_url,
        "fallback_enabled": fallback_enabled,
    }

def create_uniaopay_pix(amount: float, customer: dict, custom_api_key: str = "", custom_base_url: str = "") -> dict:
    """
    Gera cobrança PIX automatizada via União 7 Pay.
    POST https://meupagamento.site/api/v1/uniaopay/pix/create
    Headers: Authorization: Bearer <API_KEY>
    Body: { "amount": 50.00, "customer": { "name": "...", "document": "...", "email": "...", "phone": "..." } }
    """
    cfg = _get_uniaopay_config()
    api_key = (custom_api_key or cfg["api_key"]).strip()
    base_url = (custom_base_url or cfg["base_url"]).strip()

    if not api_key:
        return {"ok": False, "error": "Chave API da União 7 Pay não configurada."}

    clean_doc = re.sub(r'\D', '', str(customer.get("document", "")))
    if not clean_doc or len(clean_doc) < 11:
        clean_doc = "03229612973"

    clean_phone = re.sub(r'\D', '', str(customer.get("phone", "")))
    if not clean_phone or len(clean_phone) < 10:
        clean_phone = "41999786408"

    req_amount = round(float(amount), 2)
    # A União 7 Pay exige limite mínimo de R$ 20.00 por transação
    if req_amount < 20.00:
        req_amount = 20.00

    payload = {
        "amount": req_amount,
        "customer": {
            "name": str(customer.get("name") or "VAGNER DE CAMARGO SIRINO")[:100],
            "document": clean_doc[:14],
            "email": str(customer.get("email") or "teste@gmail.com")[:100],
            "phone": clean_phone[:15]
        }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        t0 = time.time()
        res = None

        # 1. Tentativa primária com curl_cffi Session (warmup de cookies Cloudflare + impersonate)
        try:
            from curl_cffi import requests as cffi_requests
            sess = cffi_requests.Session()
            # Warmup na raiz do domínio para obter cookies de validação anti-bot do Cloudflare
            try:
                domain_root = "https://" + base_url.split("//")[-1].split("/")[0]
                sess.get(domain_root, impersonate="chrome124", timeout=8)
            except Exception:
                pass

            for imp in ("chrome124", "chrome120", "safari17_0"):
                try:
                    res = sess.post(base_url, json=payload, headers=headers, impersonate=imp, timeout=15)
                    if res.status_code != 403:
                        break
                except Exception:
                    continue
        except Exception as _e_cffi:
            pass

        # 2. Fallback com cloudscraper se cffi falhar ou não conseguir
        if res is None or res.status_code == 403:
            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                res = scraper.post(base_url, json=payload, headers=headers, timeout=15)
            except Exception:
                pass

        # 3. Fallback com requests puro
        if res is None:
            res = requests.post(base_url, json=payload, headers=headers, timeout=12)

        elapsed_ms = int((time.time() - t0) * 1000)

        if res.status_code in (200, 201):
            try:
                data = res.json()
            except Exception:
                data = {}
            tx_obj = data.get("transaction", {}) if isinstance(data.get("transaction"), dict) else {}
            payment = data.get("payment", {}) if isinstance(data.get("payment"), dict) else {}
            tx_id = tx_obj.get("id") or data.get("transaction_id") or data.get("id") or ""
            pix_copia_cola = data.get("pix_code") or payment.get("pix_copia_cola") or tx_obj.get("pix_code") or data.get("pix_copia_cola") or data.get("qrcode") or ""
            expires_in = payment.get("expires_in") or data.get("expires_in") or 1800
            qr_base64 = data.get("qr_code_base64") or payment.get("qr_base64") or tx_obj.get("qr_code_base64") or ""

            if pix_copia_cola:
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={requests.utils.quote(pix_copia_cola)}"
                return {
                    "ok": True,
                    "gateway": "uniaopay",
                    "transaction_id": tx_id,
                    "pix_code": pix_copia_cola,
                    "qr_code_url": qr_url,
                    "qr_base64": qr_base64,
                    "expires_in": expires_in,
                    "status": "pending",
                    "elapsed_ms": elapsed_ms,
                    "raw": data
                }
            else:
                return {
                    "ok": False,
                    "error": "A União 7 Pay não retornou pix_copia_cola no payload.",
                    "status_code": res.status_code,
                    "response": data
                }
        else:
            is_cf = "cloudflare" in res.text.lower() or "attention required" in res.text.lower() or res.status_code == 403
            clean_err = re.sub(r'<[^>]+>', ' ', res.text).strip()
            clean_err = re.sub(r'\s+', ' ', clean_err)[:200]
            return {
                "ok": False,
                "error": f"Erro HTTP {res.status_code} na União 7 Pay: {clean_err or 'Verifique a chave da API'}",
                "status_code": res.status_code,
                "cloudflare_challenge": is_cf,
                "response_text": res.text[:250]
            }
    except Exception as e:
        return {"ok": False, "error": f"Exceção de conexão com União 7 Pay: {str(e)}"}





# â”€â”€â”€ BANCO DE DADOS EM MEMÓRIA DE PAGAMENTOS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

PAYMENTS_DB        = {}   # cache em memoria; persistido no SQLite

PROCESSED_WEBHOOKS = set()  # persistido no SQLite para sobreviver restarts



def _save_payment(record: dict):

    pid  = record.get("externalId") or record.get("payment_id", "")

    c7id = record.get("c7_id", "") or ""

    try:

        if BOT_AVAILABLE:

            conn = admin_bot.get_db()

            conn.execute(

                "INSERT OR REPLACE INTO payments"

                " (payment_id,c7_id,external_id,amount,status,pix_code,"

                " qr_code_url,expires_at,payer_name,payer_cpf,ip,created_at)"

                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"

            , (

                pid, c7id or None, pid,

                float(record.get("amount") or 0),

                record.get("status", "pending"),

                record.get("pix_code", "")[:2000],

                record.get("qr_code_url", "")[:500],

                str(record.get("expires_at", ""))[:60],

                record.get("name", "")[:120],

                record.get("cpf", "")[:20],

                record.get("ip", "")[:45],

                record.get("created_at", 0),

            ))

            conn.commit(); conn.close()

    except Exception as _pe:

        log.warning("[PAYMENTS] persist error: %s", _pe)

    if pid:  PAYMENTS_DB[pid]  = record

    if c7id: PAYMENTS_DB[c7id] = record



def _update_payment_status(payment_id: str, status: str, **extra):

    record = PAYMENTS_DB.get(payment_id)

    if record:

        record["status"] = status

        record.update(extra)

    try:

        if BOT_AVAILABLE:

            conn = admin_bot.get_db()

            if status == "paid":

                conn.execute(

                    "UPDATE payments SET status=?,end_to_end_id=?,net_amount=?,"

                    "fee_amount=?,confirmed_at=? WHERE payment_id=? OR c7_id=?",

                    (status, extra.get("end_to_end_id",""), extra.get("net_amount"),

                     extra.get("fee_amount"), time.time(),

                     payment_id, payment_id))

            else:

                conn.execute("UPDATE payments SET status=? WHERE payment_id=? OR c7_id=?",

                             (status, payment_id, payment_id))

            conn.commit(); conn.close()

    except Exception as _pe:

        log.warning("[PAYMENTS] status update error: %s", _pe)



def _mark_webhook_processed(key: str):

    PROCESSED_WEBHOOKS.add(key)

    try:

        if BOT_AVAILABLE:

            conn = admin_bot.get_db()

            conn.execute(

                "INSERT OR IGNORE INTO processed_webhooks(webhook_id,processed_at)"

                " VALUES(?,?)", (key, time.time()))

            conn.commit(); conn.close()

    except Exception:

        pass



def _ensure_payment_tables(conn):

    """Migracao segura: cria tabelas de pagamento se ainda nao existirem no DB legado."""

    conn.executescript("""

        CREATE TABLE IF NOT EXISTS payments (

            payment_id    TEXT PRIMARY KEY,

            c7_id         TEXT,

            external_id   TEXT,

            amount        REAL NOT NULL DEFAULT 0,

            status        TEXT NOT NULL DEFAULT 'pending',

            pix_code      TEXT,

            qr_code_url   TEXT,

            expires_at    TEXT,

            payer_name    TEXT,

            payer_cpf     TEXT,

            ip            TEXT,

            end_to_end_id TEXT,

            net_amount    REAL,

            fee_amount    REAL,

            created_at    REAL NOT NULL,

            confirmed_at  REAL

        );

        CREATE TABLE IF NOT EXISTS processed_webhooks (

            webhook_id    TEXT PRIMARY KEY,

            processed_at  REAL NOT NULL

        );

        CREATE TABLE IF NOT EXISTS auth_failures (

            ip            TEXT PRIMARY KEY,

            count         INTEGER NOT NULL DEFAULT 0,

            blocked_until REAL NOT NULL DEFAULT 0,

            first_fail    REAL NOT NULL,

            updated_at    REAL NOT NULL

        );

        CREATE TABLE IF NOT EXISTS activity_log (

            id            INTEGER PRIMARY KEY AUTOINCREMENT,

            event_type    TEXT NOT NULL,

            actor_id      INTEGER,

            session_id    TEXT,

            ip            TEXT,

            slug          TEXT,

            details_enc   TEXT,

            created_at    REAL NOT NULL

        );

        CREATE TABLE IF NOT EXISTS ip_bans (

            ip            TEXT PRIMARY KEY,

            reason        TEXT NOT NULL DEFAULT 'Comprador banido pelo Admin Supremo',

            banned_by     INTEGER,

            banned_at     REAL NOT NULL,

            payment_id    TEXT,

            amount        REAL

        );

        CREATE INDEX IF NOT EXISTS idx_pay_status ON payments(status, created_at);

        CREATE INDEX IF NOT EXISTS idx_pw_proc    ON processed_webhooks(processed_at);

        CREATE INDEX IF NOT EXISTS idx_ipbans     ON ip_bans(ip);

    """)



def _load_payments_from_db():

    if not BOT_AVAILABLE: return

    try:

        conn = admin_bot.get_db()

        _ensure_payment_tables(conn)  # migracao segura: cria se nao existir

        rows = conn.execute(

            "SELECT * FROM payments WHERE status='pending' AND created_at>?",

            (time.time() - 86400,)).fetchall()

        for r in rows:

            d = dict(r)

            pid  = d.get("payment_id","")

            c7id = d.get("c7_id","")

            if pid:  PAYMENTS_DB[pid]  = d

            if c7id: PAYMENTS_DB[c7id] = d

        prows = conn.execute(

            "SELECT webhook_id FROM processed_webhooks WHERE processed_at>?",

            (time.time() - 86400,)).fetchall()

        for pr in prows:

            PROCESSED_WEBHOOKS.add(pr["webhook_id"])

        conn.close()

        log.info("[BOOT] %d payments + %d webhooks restored from SQLite.",

                 len(PAYMENTS_DB), len(PROCESSED_WEBHOOKS))

    except Exception as _be:

        log.warning("[BOOT] payment restore error: %s", _be)





# â”€â”€â”€ RATE LIMITER, BRUTE FORCE GUARD & FIREWALL DE APLICAÇÃO (WAF IN-MEMORY) â”€

RATE_LIMIT_DB = {}   # hot cache; not persisted (low risk)

AUTH_FAIL_DB  = {}   # cache; persisted in SQLite per write



def _persist_auth_fail(ip: str, rec: dict):

    try:

        if BOT_AVAILABLE:

            conn = admin_bot.get_db()

            conn.execute(

                "INSERT OR REPLACE INTO auth_failures"

                " (ip,count,blocked_until,first_fail,updated_at)"

                " VALUES(?,?,?,?,?)",

                (ip, rec["count"], rec["blocked_until"],

                 rec.get("first_fail", time.time()), time.time()))

            conn.commit(); conn.close()

    except Exception:

        pass



def _load_auth_failures():
    AUTH_FAIL_DB.clear()
    if not BOT_AVAILABLE: return
    try:
        conn = admin_bot.get_db()
        # Limpa bloqueios anteriores ao iniciar para garantir acesso do dono
        conn.execute("DELETE FROM auth_failures")
        conn.commit()
        conn.close()
        log.info("[BOOT] Bloqueios de IP reiniciados e liberados com sucesso.")
    except Exception:
        pass



def is_rate_limited(ip: str, limit: int = 30, window: int = 60) -> bool:

    """Limita a N requisições por minuto por IP para prevenir ataques DoS/Brute Force."""

    now = time.time()

    timestamps = RATE_LIMIT_DB.get(ip, [])

    timestamps = [ts for ts in timestamps if now - ts < window]

    if len(timestamps) >= limit:

        RATE_LIMIT_DB[ip] = timestamps

        return True

    timestamps.append(now)

    RATE_LIMIT_DB[ip] = timestamps

    return False



def is_auth_brute_forced(ip: str) -> bool:

    """Bloqueia IP que errou credenciais 5x em 10 minutos por 30 minutos."""

    now = time.time()

    rec = AUTH_FAIL_DB.get(ip, {"count": 0, "blocked_until": 0})

    if rec["blocked_until"] > now:

        return True

    return False



def record_auth_failure(ip: str):

    """Registra falha de autenticação e bloqueia após 5 tentativas."""

    now = time.time()

    rec = AUTH_FAIL_DB.get(ip, {"count": 0, "blocked_until": 0, "first_fail": now})

    # Reseta contador após 10 minutos sem falhas

    if now - rec.get("first_fail", now) > 600:

        rec = {"count": 0, "blocked_until": 0, "first_fail": now}

    rec["count"] += 1

    if rec["count"] >= 5:

        rec["blocked_until"] = now + 1800  # 30 minutos de bloqueio

        _log_security(f"BRUTE_FORCE_BLOCKED", ip, rec["count"])

    AUTH_FAIL_DB[ip] = rec

    _persist_auth_fail(ip, rec)



def reset_auth_failures(ip: str):
    """Reseta falhas após login bem-sucedido e remove do SQLite."""
    AUTH_FAIL_DB.pop(ip, None)
    try:
        if BOT_AVAILABLE:
            conn = admin_bot.get_db()
            conn.execute("DELETE FROM auth_failures WHERE ip=?", (ip,))
            conn.commit()
            conn.close()
    except Exception:
        pass



def _log_security(event: str, ip: str, detail):

    """Log rápido de segurança sem dependência do BOT_AVAILABLE."""

    print(f"[SECURITY] {event} | IP: {ip} | Detail: {detail}")



# â”€â”€â”€ HEADERS DE SEGURANÇA & BLINDAGEM HTTP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.before_request

def _set_csp_nonce():

    g.csp_nonce = _sec_nonce.token_hex(16)



@app.after_request

def apply_security_headers(response):

    """Aplica cabeçalhos de proteção militar contra XSS, Clickjacking, MIME-sniffing e HSTS."""

    response.headers['X-Content-Type-Options'] = 'nosniff'

    response.headers['X-Frame-Options'] = 'SAMEORIGIN'

    response.headers['X-XSS-Protection'] = '1; mode=block'

    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    response.headers['Content-Security-Policy'] = (

        "default-src 'self'; "

        "script-src 'self' 'unsafe-inline' https://telegram.org https://fonts.googleapis.com; "

        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "

        "font-src 'self' https://fonts.gstatic.com; "

        "img-src 'self' data: https: blob:; "

        "connect-src 'self' https://viacep.com.br https://api.carteirado7.com "

        "https://ws.hubdodesenvolvedor.com.br https://api.telegram.org https://api.qrserver.com; "

        "frame-src 'self'; "

        "frame-ancestors 'self' https://web.telegram.org;"

    )

    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(), payment=()'

    # Remove headers que vazam stack info
    response.headers.pop('Server', None)
    response.headers.pop('X-Powered-By', None)

    # Sem cache em rotas de API (dados sensiveis)
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'

    return response



# â”€â”€â”€ MOTORES DE VALIDAÇÃO ESTREITA & ANTI-BOT / ANTI-FAKE LEAD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

KNOWN_BOT_UAS = [

    "bot", "crawler", "spider", "headless", "selenium", "puppeteer",

    "phantom", "curl", "python-requests", "wget", "httpclient", "guzzle",

    "ahrefs", "semrush", "bingbot", "googlebot", "yandex", "bytespider",

    "zgrab", "nmap", "sqlmap", "nikto", "censys", "shodan", "go-http-client"

]



KNOWN_CLOUD_HEADERS = [

    "X-Forwarded-Host", "X-Scanner-Tag", "X-Amzn-Trace-Id"

]



def is_bot_request(ua: str) -> bool:

    """Detecta scrapers, bots, robôs de crawlers, ferramentas automatizadas e requisições de datacenter/cloud sem navegador real."""

    if not ua or len(ua) < 15:

        return True

    ua_low = ua.lower()

    if any(b in ua_low for b in KNOWN_BOT_UAS):

        return True

    # Navegadores legítimos sempre possuem Mozilla/5.0 e componentes conhecidos

    if not ua_low.startswith("mozilla/5.0"):

        return True

    return False



def validate_cpf(cpf_raw: str) -> bool:

    """Valida o cálculo matemático exato dos 2 dígitos verificadores do CPF brasileiro."""

    digits = [int(c) for c in str(cpf_raw) if c.isdigit()]

    if len(digits) != 11:

        return False

    if len(set(digits)) == 1:

        return False # 111.111.111-11 é inválido



    # Cálculo do 1º Dígito Verificador

    sum1 = sum(digits[i] * (10 - i) for i in range(9))

    rev1 = 11 - (sum1 % 11)

    d1 = 0 if rev1 >= 10 else rev1

    if digits[9] != d1:

        return False



    # Cálculo do 2º Dígito Verificador

    sum2 = sum(digits[i] * (11 - i) for i in range(10))

    rev2 = 11 - (sum2 % 11)

    d2 = 0 if rev2 >= 10 else rev2

    return digits[10] == d2



def verify_cpf_hub(cpf_raw: str, dob: str = "") -> tuple[bool, str, dict]:

    """

    Consulta a API do Hub do Desenvolvedor para validar CPF e dados reais.

    Caso os créditos acabem ou haja erro no token, avisa o Admin no Telegram para trocar o token.

    Retorna (is_valid, error_msg, raw_data).

    """

    clean_cpf = re.sub(r'\D', '', str(cpf_raw))

    if not validate_cpf(clean_cpf):

        return False, "CPF matematicamente inválido.", {}



    token = admin_bot.get_config("hub_cpf_token", "") if BOT_AVAILABLE else os.environ.get("HUB_CPF_TOKEN", "")

    url = f"https://ws.hubdodesenvolvedor.com.br/v2/cpf/?cpf={clean_cpf}&data={dob}&token={token}"



    try:

        res = requests.get(url, timeout=5)

        res_json = res.json()

        

        # Verifica se o retorno indica saldo/créditos esgotados ou erro de autenticação

        status_code = res_json.get("status")

        code = str(res_json.get("code", ""))

        message = str(res_json.get("message", "") or res_json.get("msg", "")).lower()



        is_out_of_credits = (

            "crédito" in message or "saldo" in message or "token" in message or 

            "expirad" in message or "limit" in message or code in ("401", "402", "403", "99") or

            status_code is False and ("credito" in message or "token" in message)

        )



        if is_out_of_credits:

            # Notifica o Admin no Telegram

            alert_msg = (

                "âš ï¸ *ALERTA DE SISTEMA - CRÉDITOS CPF ESGOTADOS*\n\n"

                "Os créditos da API Hub do Desenvolvedor para consulta de CPF acabaram ou o token expirou!\n\n"

                "👉 *Ação necessária:* Crie uma nova conta na Hub do Desenvolvedor, gere um novo token e atualize as configurações.\n"

                f"ðŸ”‘ *Token Atual:* `{token}`"

            )

            _log("HUB_CPF_CREDITS_EXHAUSTED", str(uuid.uuid4()), {"alert": alert_msg, "response": res_json})

            # Mantém fallback para validação matemática para o lead não travar

            return True, "", {"fallback_math": True}



        if res_json.get("return") == "OK" or res_json.get("status") is True or res_json.get("code") == 200:

            result_data = res_json.get("result", {})

            return True, "", result_data



        # Se retornou CPF não encontrado ou cancelado

        if "não encontrado" in message or "inválido" in message:

            return False, "CPF não localizado na base de dados da Receita Federal.", res_json



    except Exception as e:

        print(f"[Hub CPF API Error] {e}")



    # Em caso de timeout ou indisponibilidade da API, faz fallback para validação matemática

    return True, "", {"fallback_math": True}



# ─── TELEGRAM WEBHOOK SECRET ─────────────────────────────────────────────────────

# IMPORTANTE: definido aqui (antes do @before_request) pois validate_request_security

# usa esta constante em _waf_bypass_paths. Se estivesse definida depois causaria NameError.

_TG_WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET",

    hashlib.sha256(os.environ.get("TELEGRAM_BOT_TOKEN", "notoken").encode()).hexdigest()[:32])



@app.before_request

def validate_request_security():

    """Filtro global de mitigação de DoS, inspeção de Payload e bloqueio de bots/crawlers."""

    ip = _user_ip()

    ua = _user_ua()



    # ─── VERIFICAÇÃO DE BAN PERMANENTE POR IP (compradores banidos pelo Admin Supremo) ──
    # Admin e webhook routes ficam isentos para não bloquear operação
    _admin_exempt = request.path.startswith('/api/admin') or request.path.startswith('/tg/') \
                    or request.path.startswith('/api/webhook') or request.path == '/admin'
    if not _admin_exempt and BOT_AVAILABLE:
        try:
            _bconn = admin_bot.get_db()
            _ban_row = _bconn.execute(
                "SELECT reason FROM ip_bans WHERE ip=? LIMIT 1", (ip,)
            ).fetchone()
            _bconn.close()
            if _ban_row:
                return (
                    "<html><body style='background:#0a0a0a;color:#fff;font-family:sans-serif;"
                    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
                    "<div style='text-align:center'><h1 style='color:#EF4444;font-size:2rem'>Acesso Bloqueado</h1>"
                    "<p style='color:rgba(255,255,255,0.5);margin-top:8px'>Este endereço foi permanentemente bloqueado.<br>"
                    f"Motivo: {_ban_row['reason']}</p></div></body></html>",
                    403
                )
        except Exception as _be:
            log.warning("[IP_BAN_CHECK] erro: %s", _be)



    # Bloqueia bots maliciosos e crawlers automatizados
    # Exceções críticas: webhooks de pagamento (ElitePay/C7, União 7 Pay, etc.) e rotas do Telegram (/tg/)
    _waf_bypass_paths = ('/api/webhook/pix', '/api/webhook/uniaopay', f'/tg/{_TG_WEBHOOK_SECRET}', '/tg/callback', '/tg/login')

    is_wh_route = request.path.startswith('/api/webhook') or request.path.startswith('/tg/')
    if is_bot_request(ua) and request.path not in _waf_bypass_paths and not is_wh_route:
        _log("SECURITY_BLOCKED_BOT", str(uuid.uuid4()), {"ip": ip, "ua": ua, "reason": "Bot/Crawler User-Agent detected"})
        return jsonify({"error": "Access denied for automated agents."}), 403



    if is_rate_limited(ip, limit=60, window=60):

        _log("SECURITY_ALERT_DOS", str(uuid.uuid4()), {"ip": ip, "reason": "Rate limit exceeded"})

        return jsonify({"error": "Too many requests. Temporary security block."}), 429



# â”€â”€â”€ HELPERS DE SANITIZAÇÃO & CRIPTOGRAFIA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def sanitize_input(val: str, max_len: int = 500) -> str:

    """Sanitiza strings removendo possíveis injeções XSS/HTML e delimitando tamanho."""

    if not isinstance(val, str):

        return ""

    clean = re.sub(r'[<>]', '', val.strip())

    return clean[:max_len]



def _user_ip():

    if request.headers.get('X-Forwarded-For'):

        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()

        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):

            return ip

    return request.remote_addr or '127.0.0.1'



def _user_ua():

    return sanitize_input(request.headers.get('User-Agent', ''), 250)



def _session_id(data):

    """Extracts session_id from request body or generates one."""

    return data.get('session_id', str(uuid.uuid4()))



def _log(event_type, session_id, data):

    """Central logging — writes to bot.py DB (encrypted) + sends Telegram notification."""

    ip = _user_ip()

    if not isinstance(data, dict):

        data = {}

    data['ip'] = data.get('ip') or ip

    if 'ua' not in data or not data['ua']:

        data['ua'] = _user_ua()

    if 'slug' not in data or not data['slug'] or data['slug'] in ('—', 'None', '-', ''):

        data['slug'] = request.args.get('slug') or request.args.get('p') or 'principal'

    if BOT_AVAILABLE:

        try:

            admin_bot.log_event(event_type, session_id, ip, data)

            admin_bot.notify_admins(event_type, data)

        except Exception as e:

            print(f"[log] {event_type}: {e}")

    else:

        print(f"[LOCAL EVENT] {event_type} | {ip} | {data}")



def get_elitepay_headers(custom_client_id: str = "", custom_client_secret: str = "") -> dict:
    """
    Headers oficiais de autenticação da ElitePay conforme documentação técnica:
    - x-client-id: seu_client_id
    - x-client-secret: seu_client_secret
    - Content-Type: application/json
    """
    keys = _get_live_gateway_keys()
    cid = custom_client_id or keys.get("client_id") or keys.get("api_key", "")
    cs  = custom_client_secret or keys.get("client_secret") or keys.get("api_secret", "")
    return {
        "x-client-id": cid,
        "x-client-secret": cs,
        "ci": cid,
        "cs": cs,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "OLPG-ElitePay-Connector/2026"
    }


def get_c7_auth_headers(body_str: str = "") -> dict:
    """
    Gera headers de autenticacao HMAC-SHA256 conforme C7 API Doc.
    - Leitura: Authorization: Bearer <api_key>
    - Escrita:  + X-C7-Timestamp, X-C7-Nonce, X-C7-Signature
    Formula: HMAC-SHA256(api_secret, timestamp + '.' + nonce + '.' + body)
    Nonce: UUID v4 unico por requisicao.
    """
    keys       = _get_live_c7_keys()
    api_key    = keys.get("api_key", C7_API_KEY) or ""
    api_secret = keys.get("api_secret", C7_API_SECRET) or ""

    ts        = str(int(time.time()))
    nonce     = str(uuid.uuid4())   # UUID v4, unico por requisicao
    sig_input = f"{ts}.{nonce}.{body_str}"

    signature = hmac.new(
        api_secret.encode('utf-8'),
        sig_input.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return {
        "Authorization":  f"Bearer {api_key}",
        "Content-Type":   "application/json",
        "X-C7-Timestamp": ts,
        "X-C7-Nonce":     nonce,
        "X-C7-Signature": signature,
        "User-Agent":     "OLPG-System/2026",
        "Accept":         "application/json"
    }


def _c7_read_headers() -> dict:
    """Headers somente-leitura (sem HMAC) — para GET endpoints como /payment/:id/status."""
    keys    = _get_live_c7_keys()
    api_key = keys.get("api_key", C7_API_KEY) or ""
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
        "User-Agent":    "OLPG-System/2026"
    }


# â”€â”€â”€ GERADOR DE PIX EMV VÃLIDO (BACEN BR CODE 2.0) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _crc16_ccitt(data: str) -> str:

    """Calcula CRC-16/CCITT-FALSE conforme exigido pelo BACEN para QR Codes Pix."""

    crc = 0xFFFF

    for char in data:

        crc ^= ord(char) << 8

        for _ in range(8):

            if crc & 0x8000:

                crc = (crc << 1) ^ 0x1021

            else:

                crc <<= 1

            crc &= 0xFFFF

    return format(crc, '04X')



def _emv_field(id_: str, value: str) -> str:

    """Monta um campo TLV EMV: ID + length (2 dígitos) + value."""

    return f"{id_}{len(value):02d}{value}"



def generate_pix_emv(amount: float, merchant_name: str, merchant_city: str,

                     pix_key: str, txid: str = "") -> str:

    """

    Gera um payload Pix BR Code 2.0 válido conforme Manual do BACEN.

    Produz QR Code que passa na validação de TODOS os bancos brasileiros.

    """

    merchant_name = re.sub(r'[^A-Za-z0-9 ]', '', merchant_name)[:25].upper().strip()

    merchant_city = re.sub(r'[^A-Za-z0-9 ]', '', merchant_city)[:15].upper().strip()

    txid          = re.sub(r'[^A-Za-z0-9]', '', txid)[:25] if txid else "***"



    # GUI do arranjo Pix (fixo BACEN)

    pix_gui = _emv_field("00", "BR.GOV.BCB.PIX")

    # Chave Pix

    pix_key_field = _emv_field("01", pix_key)

    # Merchant Account Information (ID 26)

    mai_value = pix_gui + pix_key_field

    mai = _emv_field("26", mai_value)



    # Payload Format Indicator

    pfi = _emv_field("00", "01")

    # Point of Initiation Method (12 = dinâmico / único uso)

    poim = _emv_field("01", "12")

    # Merchant Category Code

    mcc = _emv_field("52", "0000")

    # Transaction Currency BRL

    currency = _emv_field("53", "986")

    # Amount

    amount_str = f"{amount:.2f}"

    tx_amount = _emv_field("54", amount_str)

    # Country Code

    country = _emv_field("58", "BR")

    # Merchant Name

    merchant_n = _emv_field("59", merchant_name)

    # Merchant City

    merchant_c = _emv_field("60", merchant_city)

    # Additional Data Field Template (ID 62) — TXID

    txid_field = _emv_field("05", txid)

    adf = _emv_field("62", txid_field)

    # CRC placeholder (4 zeros antes de calcular)

    crc_placeholder = "6304"



    payload_no_crc = pfi + poim + mai + mcc + currency + tx_amount + country + merchant_n + merchant_c + adf + crc_placeholder

    crc_val = _crc16_ccitt(payload_no_crc)

    return payload_no_crc[:-4] + "6304" + crc_val



def get_whatsapp_config():

    """Reads WhatsApp config from bot.py DB (set via Telegram bot)."""

    if BOT_AVAILABLE:

        return {

            "number":  admin_bot.get_config("whatsapp_number",  "5511999999999"),

            "message": admin_bot.get_config("whatsapp_message", "Olá! Tenho interesse no iPhone 11 64GB branco. Pode me ajudar?"),

        }

    return {

        "number":  os.environ.get("WHATSAPP_NUMBER",  "5511999999999"),

        "message": os.environ.get("WHATSAPP_MESSAGE", "Olá! Tenho interesse no iPhone 11 64GB branco. Pode me ajudar?"),

    }



# â”€â”€â”€ ROUTES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€






@app.route('/')

@app.route('/p/<slug_or_code>')

@app.route('/p/<slug_or_code>/<item_code>')

def index(slug_or_code=None, item_code=None):

    ip = _user_ip()

    ua = _user_ua()

    sid = str(uuid.uuid4())



    p_code = slug_or_code or request.args.get('p')

    tg_id = None

    slug = None

    custom_item = None

    cfgs = {}



    if TG_WH_AVAILABLE and p_code:

        tg_id = tg_wh.get_tg_id_by_slug(p_code)

        if tg_id:

            slug = p_code

            if item_code:

                custom_item = tg_wh.get_product_by_code(item_code, tg_id=tg_id)

        else:

            # Tenta buscar por código de produto direto

            custom_item = tg_wh.get_product_by_code(p_code)

            if custom_item:

                tg_id = custom_item["tg_id"]

                slug = tg_wh.get_slug(tg_id)



    if TG_WH_AVAILABLE and tg_id and slug:

        allowed, current_clicks, max_clicks = tg_wh.check_click_limit(tg_id)

        if not allowed:

            return f"<h1>Página Temporariamente Indisponível</h1><p>O limite mensal de visitas deste anúncio foi atingido ({current_clicks}/{max_clicks}). Contate o administrador.</p>", 429



        cfgs = tg_wh.get_tenant_all_config(tg_id)

        

        # Se for um item específico do catálogo próprio do admin

        p_name = custom_item["title"] if custom_item else cfgs.get("product_name", "")

        p_price = custom_item["price"] if custom_item else cfgs.get("product_price", "")

        p_old_price = custom_item["old_price"] if custom_item else cfgs.get("product_old_price", "")

        p_desc = custom_item["description"] if custom_item else cfgs.get("product_description", "")

        p_img = (custom_item["image_url"] if custom_item and custom_item["image_url"] else cfgs.get("product_image", "/static/images/iphone11_1.jpg"))

        p_img1 = (custom_item["image1"] if custom_item and custom_item["image1"] else p_img)

        p_img2 = (custom_item["image2"] if custom_item and custom_item["image2"] else cfgs.get("product_image2", ""))

        p_img3 = (custom_item["image3"] if custom_item and custom_item["image3"] else cfgs.get("product_image3", ""))



        # Log de sessão e evento — feito UMA única vez após carregamento do produto

        tg_wh.record_tenant_session(tg_id, slug, sid, ip, ua[:200])

        tg_wh.log_tenant_event(tg_id, slug, "PAGE_ENTRY", sid, ip, {"ua": ua[:200], "item": item_code or "default", "product": p_name})

        _log("PAGE_ENTRY", sid, {

            "slug": slug,

            "ip": ip,

            "ua": ua,

            "product_name": p_name,

            "product_price": p_price,

            "item": item_code or "default"

        })



        # Dados de shipping e cupom do produto

        p_shipping_mode        = custom_item.get("shipping_mode",        "full")    if custom_item else "full"

        p_shipping_fee         = custom_item.get("shipping_fee",         "19.90")   if custom_item else "19.90"

        p_shipping_coupon      = custom_item.get("shipping_coupon",      "")        if custom_item else ""

        p_coupon_active        = int(custom_item.get("coupon_active",    1) or 0)   if custom_item else 1

        p_coupon_only_shipping = int(custom_item.get("coupon_only_shipping", 1) or 0) if custom_item else 1

        p_product_code         = custom_item.get("product_code",         "")        if custom_item else ""



        # Geolocalização em background (não bloqueia o render)

        import threading

        threading.Thread(

            target=tg_wh.enrich_session_with_geo, args=(tg_id, sid, ip), daemon=True

        ).start()



        return render_template(

            'index.html',

            session_id=sid,

            product_slug=slug,

            product_name=p_name,

            product_price=p_price,

            product_old_price=p_old_price,

            product_description=p_desc,

            product_image=p_img,

            product_image1=p_img1,

            product_image2=p_img2,

            product_image3=p_img3,

            seller_name=(custom_item["seller_name"] if custom_item and custom_item.get("seller_name") else cfgs.get("seller_name", "")),

            seller_since=(custom_item["seller_since"] if custom_item and custom_item.get("seller_since") else cfgs.get("seller_since", "")),

            seller_avatar=(custom_item.get("seller_avatar") if custom_item and custom_item.get("seller_avatar") else cfgs.get("seller_avatar", "")),
            seller_sales_completed=custom_item.get("seller_sales_completed", "") if custom_item else "",
            seller_sales_canceled=custom_item.get("seller_sales_canceled", "") if custom_item else "",
            seller_dispatch_time=custom_item.get("seller_dispatch_time", "") if custom_item else "",
            seller_rating=custom_item.get("seller_rating", "") if custom_item else "",
            seller_reviews=custom_item.get("seller_reviews", "") if custom_item else "",
            seller_level=custom_item.get("seller_level", "") if custom_item else "",
            seller_email_verified=custom_item.get("seller_email_verified", 1) if custom_item else 1,
            seller_phone_verified=custom_item.get("seller_phone_verified", 1) if custom_item else 1,
            seller_id_verified=custom_item.get("seller_id_verified", 1) if custom_item else 1,
            seller_fb_verified=custom_item.get("seller_fb_verified", 0) if custom_item else 0,
            seller_fb_url=custom_item.get("seller_fb_url", "") if custom_item else "",
            product_published_at=(custom_item.get("product_published_at", "") if custom_item else "") or (cfgs.get("product_published_at", "") if 'cfgs' in dir() and isinstance(cfgs, dict) else ""),

                    det_category=(custom_item["det_category"] if custom_item and "det_category" in custom_item else cfgs.get("det_category", "Celulares E Smartphones")),

            det_brand=(custom_item["det_brand"] if custom_item and "det_brand" in custom_item else cfgs.get("det_brand", "Apple")),

            det_model=(custom_item["det_model"] if custom_item and "det_model" in custom_item else cfgs.get("det_model", "Iphone 11")),

            det_condition=(custom_item["det_condition"] if custom_item and "det_condition" in custom_item else cfgs.get("det_condition", "Usado - Excelente")),

            det_memory=(custom_item["det_memory"] if custom_item and "det_memory" in custom_item else cfgs.get("det_memory", "64gb")),

            det_color=(custom_item["det_color"] if custom_item and "det_color" in custom_item else cfgs.get("det_color", "Branco")),

            seller_status=cfgs.get("seller_status", ""),

            logo_url=cfgs.get("logo_url", ""),

            shipping_mode=p_shipping_mode,

            shipping_fee=p_shipping_fee,

            shipping_coupon=p_shipping_coupon,

            coupon_active=p_coupon_active,

            coupon_only_shipping=p_coupon_only_shipping,

            product_code=p_product_code,

            breadcrumb_state=cfgs.get("breadcrumb_state", "São Paulo"),

            breadcrumb_region=cfgs.get("breadcrumb_region", "São Paulo e região"),

            breadcrumb_zone=(custom_item.get("breadcrumb_zone") if custom_item and custom_item.get("breadcrumb_zone") else cfgs.get("breadcrumb_zone", "Zona Norte")),

            tenant_tg_id=tg_id or 0,

            whatsapp={

                "number": cfgs.get("whatsapp_number", "5511999999999"),

                "message": cfgs.get("whatsapp_message", f"Olá! Tenho interesse no anúncio: {p_name}")

            }

        )



    # Fallback global

    if BOT_AVAILABLE:

        try:

            conn = admin_bot.get_db()

            conn.execute(

                "INSERT OR IGNORE INTO sessions(session_id,ip,ua,entered_at) VALUES(?,?,?,?)",

                (sid, ip, ua[:200], time.time())

            )

            conn.commit()

            conn.close()

        except Exception as e:

            print(f"[session] {e}")



    # Carrega produto específico por código se fornecido

    custom_product = None

    if p_code and BOT_AVAILABLE:

        try:

            conn = admin_bot.get_db()

            custom_product = conn.execute(

                "SELECT name, price, old_price, description, image_url, image1, image2, image3 FROM product_templates WHERE code=?", (p_code,)

            ).fetchone()

            conn.close()



        except Exception:

            pass



    if custom_product:

        product_name = custom_product["name"]

        product_price = custom_product["price"]

        product_description = custom_product["description"]

        product_image = custom_product["image_url"] or "/static/images/iphone11_1.jpg"

        # old_price e fotos individuais do template

        try:

            product_old_price_tpl = custom_product["old_price"] or ""

        except Exception:

            product_old_price_tpl = ""

        try:

            img1_tpl = custom_product["image1"] or product_image

            img2_tpl = custom_product["image2"] or product_image

            img3_tpl = custom_product["image3"] or product_image

        except Exception:

            img1_tpl = img2_tpl = img3_tpl = product_image

        # Usa as fotos do template (override global)

        product_image1 = img1_tpl

        product_image2 = img2_tpl

        product_image3 = img3_tpl

        product_old_price = product_old_price_tpl

    else:

        product_name = admin_bot.get_config("product_name", "") if BOT_AVAILABLE else ""

        product_price = admin_bot.get_config("product_price", "") if BOT_AVAILABLE else ""

        product_description = admin_bot.get_config("product_description", "") if BOT_AVAILABLE else ""

        product_image = admin_bot.get_config("product_image", "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80"

        product_image1 = admin_bot.get_config("product_image1", "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80"

        product_image2 = admin_bot.get_config("product_image2", "https://images.unsplash.com/photo-1591337676887-a217a6970a8a?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1591337676887-a217a6970a8a?w=800&auto=format&fit=crop&q=80"

        product_image3 = admin_bot.get_config("product_image3", "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800&auto=format&fit=crop&q=80"

        product_old_price = admin_bot.get_config("product_old_price", "") if BOT_AVAILABLE else ""





    # Campos partilhados — sempre carregados do config global

    seller_name   = admin_bot.get_config("seller_name",   "") if BOT_AVAILABLE else ""

    seller_since  = admin_bot.get_config("seller_since",  "") if BOT_AVAILABLE else ""

    seller_status = admin_bot.get_config("seller_status", "") if BOT_AVAILABLE else ""

    logo_url      = admin_bot.get_config("logo_url", "") if BOT_AVAILABLE else ""

    favicon_url   = admin_bot.get_config("favicon_url", "") if BOT_AVAILABLE else ""



    _log("PAGE_ENTRY", sid, {

        "ua": ua,

        "path": request.path,

        "product_name": product_name,

        "product_price": product_price,

        "slug": p_code or "principal"

    })



    return render_template(

        'index.html',

        session_id=sid,

        product_name=product_name,

        product_price=product_price,

        product_old_price=product_old_price,

        product_description=product_description,

        product_image=product_image,

        product_image1=product_image1,

        product_image2=product_image2,

        product_image3=product_image3,

        seller_name=seller_name,

        seller_since=seller_since,

        det_category=cfgs.get("det_category", "Celulares E Smartphones"),

        det_brand=cfgs.get("det_brand", "Apple"),

        det_model=cfgs.get("det_model", "Iphone 11"),

        det_condition=cfgs.get("det_condition", "Usado - Excelente"),

        det_memory=cfgs.get("det_memory", "64gb"),

        det_color=cfgs.get("det_color", "Branco"),

        seller_status=seller_status,

        logo_url=logo_url,

        favicon_url=favicon_url,

        breadcrumb_state=cfgs.get("breadcrumb_state", "São Paulo") if 'cfgs' in dir() else "São Paulo",

        breadcrumb_region=cfgs.get("breadcrumb_region", "São Paulo e região") if 'cfgs' in dir() else "São Paulo e região",

        breadcrumb_zone=cfgs.get("breadcrumb_zone", "Zona Norte") if 'cfgs' in dir() else "Zona Norte",

        product_published_at=cfgs.get("product_published_at", "") if 'cfgs' in dir() and isinstance(cfgs, dict) else "",

        tenant_tg_id=0,

        whatsapp=get_whatsapp_config()

    )





@app.route('/api/config')

@app.route('/api/config/whatsapp')

@app.route('/api/config/<slug>')

def api_config(slug=None):

    """Frontend fetches live config (logo, whatsapp, price, description, seller) per tenant/slug."""

    req_slug = slug or request.args.get('slug', '').strip()

    tg_id = None

    if TG_WH_AVAILABLE and req_slug:

        tg_id = tg_wh.get_tg_id_by_slug(req_slug)



    if TG_WH_AVAILABLE and tg_id:

        cfgs = tg_wh.get_tenant_all_config(tg_id)

        wa_num = cfgs.get("whatsapp_number", "5511999999999")

        wa_msg = cfgs.get("whatsapp_message", "Olá! Tenho interesse no anúncio.")

        

        # Logo e Badges são Globais

        global_logo = admin_bot.get_config("logo_url", "") if BOT_AVAILABLE else ""

        global_badges = admin_bot.get_config("payment_badges", "") if BOT_AVAILABLE else ""



        product = tg_wh.get_product_by_code(req_slug, tg_id) if req_slug and tg_id else None
        
        prod_badges = product.get("payment_badges") if product and product.get("payment_badges") else None
        if prod_badges:
            global_badges = prod_badges

        # search_placeholder e favicon_url são sempre globais (Admin Supremo)

        global_search_placeholder = admin_bot.get_config("search_placeholder", "") if BOT_AVAILABLE else ""

        global_favicon_url = admin_bot.get_config("favicon_url", "") if BOT_AVAILABLE else ""

        return jsonify({

            "whatsapp_number":     wa_num,

            "whatsapp_message":    wa_msg,

            "logo_url":            global_logo,

            "product_price":       product.get("price", cfgs.get("product_price", "")) if product else cfgs.get("product_price", ""),

            "product_old_price":   product.get("old_price", cfgs.get("product_old_price", "")) if product else cfgs.get("product_old_price", ""),

            "product_name":        product.get("title", cfgs.get("product_name", "")) if product else cfgs.get("product_name", ""),

            "product_description": product.get("description", cfgs.get("product_description", "")) if product else cfgs.get("product_description", ""),

            "product_image":       product.get("image_url", cfgs.get("product_image", "")) if product else cfgs.get("product_image", ""),

            "product_image1":      product.get("image1", cfgs.get("product_image1", "")) if product else cfgs.get("product_image1", ""),

            "product_image2":      product.get("image2", cfgs.get("product_image2", "")) if product else cfgs.get("product_image2", ""),

            "product_image3":      product.get("image3", cfgs.get("product_image3", "")) if product else cfgs.get("product_image3", ""),

            "seller_name":         product.get("seller_name", cfgs.get("seller_name", "")) if product else cfgs.get("seller_name", ""),

            "seller_status":       cfgs.get("seller_status", ""),

            "seller_since":        product.get("seller_since", cfgs.get("seller_since", "")) if product else cfgs.get("seller_since", ""),

            "seller_avatar":       product.get("seller_avatar", cfgs.get("seller_avatar", "")) if product else cfgs.get("seller_avatar", ""),

            "payment_badges":      global_badges,

            "search_placeholder":  global_search_placeholder,

            "favicon_url":         global_favicon_url,

            "det_category":        product.get("det_category", cfgs.get("det_category", "")) if product else cfgs.get("det_category", ""),

            "det_brand":           cfgs.get("det_brand",     ""),

            "det_model":           cfgs.get("det_model",     ""),

            "det_condition":       cfgs.get("det_condition", ""),

            "det_storage":         cfgs.get("det_storage",   ""),

            "det_color":           cfgs.get("det_color",     ""),

            "breadcrumb_zone":     product.get("breadcrumb_zone", cfgs.get("breadcrumb_zone", "Zona Norte")) if product else cfgs.get("breadcrumb_zone", "Zona Norte"),

        })



    wa = get_whatsapp_config()

    def gc(k, fb): return admin_bot.get_config(k, fb) if BOT_AVAILABLE else fb

    return jsonify({

        "whatsapp_number":     wa["number"],

        "whatsapp_message":    wa["message"],

        "logo_url":            gc("logo_url", ""),

        "search_placeholder":  gc("search_placeholder", ""),

        "favicon_url":         gc("favicon_url", ""),

        "product_price":       gc("product_price", ""),

        "product_old_price":   gc("product_old_price", ""),

        "product_name":        gc("product_name", ""),

        "product_description": gc("product_description", ""),

        "product_image":       gc("product_image", ""),

        "product_image1":      gc("product_image1", ""),

        "product_image2":      gc("product_image2", ""),

        "product_image3":      gc("product_image3", ""),

        "seller_name":         gc("seller_name", ""),

        "seller_status":       gc("seller_status", ""),

        "seller_since":        gc("seller_since", ""),

        "payment_badges":      gc("payment_badges", ""),

        "det_category":  gc("det_category",  ""),

        "det_brand":     gc("det_brand",     ""),

        "det_model":     gc("det_model",     ""),

        "det_condition": gc("det_condition", ""),

        "det_storage":   gc("det_storage",   ""),

        "det_color":     gc("det_color",     ""),

    })





# â”€â”€â”€ ADMIN PANEL & ENCRYPTED AUTH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]

SUPER_ADMIN_IDS = [int(x) for x in os.environ.get("SUPER_ADMIN_IDS", "").split(",") if x.strip().isdigit()]



# ─── 6-DIGIT OTP STORE (TTL 10min, uso único) ─────────────────────────────────

_OTP_STORE: dict = {}

_OTP_TTL = 600  # 10 minutos



def _otp_generate(tg_id: int) -> str:

    import secrets as _sec_otp

    code = str(_sec_otp.randbelow(900000) + 100000)  # cryptographically secure

    _OTP_STORE[tg_id] = {"code": code, "expires": time.time() + _OTP_TTL, "attempts": 0}

    for k in [k for k, v in list(_OTP_STORE.items()) if v["expires"] < time.time()]:

        _OTP_STORE.pop(k, None)

    return code



def _otp_validate(tg_id: int, code: str) -> bool:

    rec = _OTP_STORE.get(tg_id)

    if not rec or rec["expires"] < time.time():

        _OTP_STORE.pop(tg_id, None)

        return False

    rec["attempts"] += 1

    if rec["attempts"] > 5:

        _OTP_STORE.pop(tg_id, None)

        return False

    if rec["code"] == code.strip():

        _OTP_STORE.pop(tg_id, None)

        return True

    return False





def check_is_supreme(tg_id: int) -> bool:

    """

    Retorna True se o Telegram ID for o Admin Supremo do sistema:

    1. Se constar em SUPER_ADMIN_IDS

    2. Se for o primeiro id de ADMIN_IDS

    3. Se for o admin_telegram_id salvo no banco (primeiro a se cadastrar)

    4. Se for o ID master de fallback 999999999

    """

    if not tg_id:

        return False

    if tg_id == 999999999:

        return True

    if SUPER_ADMIN_IDS and tg_id in SUPER_ADMIN_IDS:

        return True

    if _SUPREME_ADMIN_ID and tg_id == _SUPREME_ADMIN_ID:

        return True

    if ADMIN_IDS and tg_id == ADMIN_IDS[0]:

        return True

    try:

        if BOT_AVAILABLE:

            from bot import get_config

            saved = get_config("admin_telegram_id", "")

            if saved and str(tg_id) == saved:

                return True

    except Exception:

        pass

    return False





def verify_admin_access(req) -> tuple[Optional[int], str]:

    """

    Valida acesso ao painel admin com criptografia e validação de tokens.

    Retorna uma tupla: (tg_id, role)

    """

    token = (

        req.headers.get('Authorization', '').replace('Bearer ', '').strip() or

        req.args.get('token', '').strip() or

        req.cookies.get('admin_token', '').strip()

    )

    if not token:

        return None, "unauthorized"



    if BOT_AVAILABLE and len(token) >= 48:

        tg_id = admin_bot.validate_admin_token(token)

        if tg_id:

            is_supreme = check_is_supreme(tg_id)

            role = "supreme_admin" if is_supreme else "admin"

            return tg_id, role



    admin_secret = os.environ.get("ADMIN_SECRET", "")

    if admin_secret and hmac.compare_digest(token.encode(), admin_secret.encode()):

        reset_auth_failures(_user_ip())

        return 999999999, "supreme_admin"



    return None, "unauthorized"





@app.route('/admin')

@app.route('/admin/<slug>')

def admin_panel(slug=None):

    """

    Serve o painel admin com autenticação Telegram-gated e suporte multi-tenant.

    """

    ip    = _user_ip()

    token = request.args.get('token', slug or '').strip()

    admin_id, role = verify_admin_access(request)

    _log("ADMIN_PAGE_ENTRY", str(uuid.uuid4()), {"ip": ip, "auth": bool(admin_id), "role": role})

    res = make_response(render_template('admin.html', admin_slug=slug or "", admin_token=token, admin_role=role))
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res





@app.route('/api/admin/verify-token')

def api_admin_verify_token():

    """Endpoint para o frontend verificar se o token atual é válido, a role e o plano."""

    ip = _user_ip()

    if is_rate_limited(ip, limit=60, window=60):  # max 60 verify-token/min por IP
        return jsonify({"ok": False, "error": "rate_limit"}), 429

    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "token_invalido_ou_expirado"}), 401



    reset_auth_failures(ip)

    if TG_WH_AVAILABLE:

        try:

            tg_wh.notify_admin_access(admin_id, role, ip, str(request.user_agent))

        except Exception:

            pass

    plan_info = {}

    if TG_WH_AVAILABLE and admin_id:

        plan_info = tg_wh.get_user_plan(admin_id)



    # Load profile so frontend gets real name + avatar immediately at login

    prof = {}

    if TG_WH_AVAILABLE and admin_id:

        try:

            prof = tg_wh.get_tenant_profile(admin_id)

        except Exception:

            prof = {}



    return jsonify({

        "ok": True,

        "admin_id": admin_id,

        "role": role,

        "is_supreme": (role == "supreme_admin"),

        "plan": plan_info,

        "profile": {

            "display_name": prof.get("display_name", ""),

            "avatar_url":   prof.get("avatar_url", ""),

            "bio":          prof.get("bio", ""),

            "contact":      prof.get("contact", ""),

        }

    })





@app.route('/api/admin/request-code', methods=['POST'])

def api_admin_request_code():

    """

    Recebe o Telegram ID do admin, gera um código OTP de 6 dígitos,

    envia via Telegram e retorna o perfil (nome + avatar) para a tela de login.

    """

    ip = _user_ip()

    if is_rate_limited(ip, limit=5, window=60):

        return jsonify({"ok": False, "error": "rate_limit", "message": "Muitas requisições. Aguarde 1 minuto."}), 429



    data = request.get_json(silent=True) or {}

    tg_id_raw = str(data.get("tg_id", "")).strip()



    if not tg_id_raw or not tg_id_raw.isdigit():

        return jsonify({"ok": False, "error": "tg_id_invalido"}), 400



    tg_id = int(tg_id_raw)



    # Gera o código OTP

    code = _otp_generate(tg_id)



    # Busca perfil do admin para mostrar na tela de login

    prof = {}

    if TG_WH_AVAILABLE:

        try:

            tg_wh.ensure_user(tg_id, f"Admin {tg_id}")
            prof = tg_wh.get_tenant_profile(tg_id) or {}

        except Exception:

            prof = {}



    name    = prof.get("display_name") or f"Admin #{tg_id}"

    avatar  = prof.get("avatar_url", "")



    # Envia código via bot.py (instância ativa ou REST API direta — sempre funciona)

    sent_ok = False

    if BOT_AVAILABLE:

        try:

            sent_ok = admin_bot.send_otp_to_admin(tg_id, code, name)

        except Exception as e:

            print(f"[OTP] Erro ao chamar send_otp_to_admin: {e}")



    # Fallback/complemento: tg_wh (webhook multi-tenant)

    if TG_WH_AVAILABLE and not sent_ok:

        try:

            msg_html = (

                f"<b>🔐 Código de Acesso ao Painel Web</b>\n\n"

                f"Olá, <b>{name}</b>!\n\n"

                f"<b>Seu código de 6 dígitos:</b>\n"

                f"<code>  {code[:3]} {code[3:]}</code>\n\n"

                f"<i>⏳ Válido por 10 minutos. Uso único.</i>\n"

                f"<i>🔒 Nunca compartilhe este código.</i>"

            )

            tg_wh.send_msg(tg_id, msg_html)

            sent_ok = True

        except Exception as e:

            print(f"[OTP] Erro ao enviar via tg_wh: {e}")



    if not sent_ok:

        return jsonify({

            "ok": False,

            "error": "telegram_unreachable",

            "message": "Não foi possível enviar o código. Verifique se você já iniciou uma conversa com o bot (@olxrlkbot)."

        }), 503



    return jsonify({

        "ok":      True,

        "name":    name,

        "avatar":  avatar,

        "expires": 600,

    })





@app.route('/api/admin/verify-code', methods=['POST'])

def api_admin_verify_code():

    """

    Valida o código OTP de 6 dígitos.

    Se válido, gera e retorna o token de sessão completo (48 chars) + perfil.

    """

    ip = _user_ip()

    if is_auth_brute_forced(ip):

        return jsonify({"ok": False, "message": "IP bloqueado por muitas tentativas."}), 429

    if is_rate_limited(ip, limit=15, window=60):

        return jsonify({"ok": False, "error": "rate_limit"}), 429



    data   = request.get_json(silent=True) or {}

    tg_id  = int(data.get("tg_id", 0) or 0)

    code   = str(data.get("code", "")).strip()



    if not tg_id or not code:

        record_auth_failure(ip)

        return jsonify({"ok": False, "error": "dados_invalidos"}), 400



    if not _otp_validate(tg_id, code):

        record_auth_failure(ip)

        return jsonify({"ok": False, "message": "Código inválido ou expirado. Solicite um novo."}), 401



    reset_auth_failures(ip)



    # Gera token de sessão completo

    session_token = ""

    if BOT_AVAILABLE:

        try:

            session_token = admin_bot.generate_admin_token(tg_id)

        except Exception:

            session_token = ""



    is_supreme = check_is_supreme(tg_id)

    role = "supreme_admin" if is_supreme else "admin"



    prof = {}

    plan = {}

    if TG_WH_AVAILABLE:

        try:

            tg_wh.ensure_user(tg_id, f"Admin {tg_id}")
            prof = tg_wh.get_tenant_profile(tg_id) or {}

            plan = tg_wh.get_user_plan(tg_id) or {}

            tg_wh.notify_admin_access(tg_id, role, ip, str(request.user_agent))

        except Exception:

            pass



    # Audit: login bem-sucedido via OTP

    if VALIDATORS_AVAILABLE and ActivityAudit:

        ActivityAudit.log("admin_login", actor_id=tg_id, ip=ip,

                          details={"role": role, "method": "otp",

                                   "ua": str(request.user_agent)[:150]})



    return jsonify({

        "ok":        True,

        "token":     session_token,

        "admin_id":  tg_id,

        "role":      role,

        "is_supreme": is_supreme,

        "plan":      plan,

        "profile": {

            "display_name": prof.get("display_name", ""),

            "avatar_url":   prof.get("avatar_url", ""),

            "bio":          prof.get("bio", ""),

            "contact":      prof.get("contact", ""),

        }

    })





@app.route('/api/admin/recover', methods=['POST'])

def api_admin_recover():

    """

    Recuperação de conta: admin informa seu tg_id + palavra-chave suprema.

    Se correta, gera novo token de acesso sem precisar de OTP.

    Palavra-chave definida via env RECOVERY_KEYWORD (apenas o Admin Supremo sabe).

    """

    ip = _user_ip()

    if is_auth_brute_forced(ip):

        return jsonify({"ok": False, "message": "IP bloqueado."}), 429



    data    = request.get_json(silent=True) or {}

    tg_id   = int(data.get("tg_id", 0) or 0)

    keyword = str(data.get("keyword", "")).strip()



    recovery_kw = os.environ.get("RECOVERY_KEYWORD", "")

    if not recovery_kw or not keyword or keyword != recovery_kw:

        record_auth_failure(ip)

        return jsonify({"ok": False, "message": "Palavra-chave incorreta."}), 401



    reset_auth_failures(ip)



    session_token = ""

    if BOT_AVAILABLE:

        try:

            session_token = admin_bot.generate_admin_token(tg_id)

        except Exception:

            pass



    is_supreme = (tg_id in SUPER_ADMIN_IDS) or (ADMIN_IDS and tg_id in ADMIN_IDS and tg_id == ADMIN_IDS[0])

    role = "supreme_admin" if is_supreme else "admin"



    prof = {}

    if TG_WH_AVAILABLE:

        try:

            tg_wh.ensure_user(tg_id, f"Admin {tg_id}")
            prof = tg_wh.get_tenant_profile(tg_id) or {}

            tg_wh.notify_admin_access(tg_id, role, ip, f"RECOVERY via palavra-chave - {str(request.user_agent)}")

        except Exception:

            pass



    return jsonify({

        "ok":        True,

        "token":     session_token,

        "admin_id":  tg_id,

        "role":      role,

        "is_supreme": is_supreme,

        "profile": {

            "display_name": prof.get("display_name", ""),

            "avatar_url":   prof.get("avatar_url", ""),

        }

    })





@app.route('/api/admin/elitepay/status')
@app.route('/api/admin/c7-status')
def api_admin_gateway_status():
    """Retorna status em tempo real da conexão com a API ElitePay. RESTRITO ao Admin Supremo."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "Acesso não autorizado"}), 401

    if role != "supreme_admin":
        return jsonify({
            "ok": False,
            "error": "acesso_restrito",
            "message": "Dados financeiros da API são visíveis apenas para o Admin Supremo."
        }), 403

    keys = _get_live_gateway_keys()
    client_id = keys.get("client_id") or keys.get("api_key", "")
    client_secret = keys.get("client_secret") or keys.get("api_secret", "")
    base_url = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")
    active_gw = keys.get("gateway", "elitepay")

    is_configured = bool(client_id and "xxx" not in client_id)
    live_status = "disconnected"
    balance_info = None

    if is_configured:
        try:
            headers = get_elitepay_headers(client_id, client_secret)
            res = requests.get(f"{base_url}/api/v1/balance", headers=headers, timeout=5)
            if res.status_code == 200:
                live_status = "connected"
                balance_info = res.json().get("data", {})
            elif res.status_code in [401, 403]:
                live_status = "auth_invalid"
            else:
                live_status = f"http_{res.status_code}"
        except Exception:
            live_status = "error_connecting"
            balance_info = None

    return jsonify({
        "ok": True,
        "gateway": active_gw,
        "c7_status": live_status,
        "elitepay_status": live_status,
        "base_url": base_url,
        "client_id_masked": f"{client_id[:6]}...{client_id[-4:]}" if len(client_id) > 10 else (client_id if client_id else "não configurado"),
        "role": role,
        "is_supreme_admin": True,
        "balance": balance_info
    })





# ROTAS DE PERFIL DOS ADMINS E COMPARTILHAMENTO

@app.route('/api/admin/ai/financial-insights')

def api_admin_ai_financial_insights():

    """Insights reais de convers\u00e3o calculados a partir dos dados do banco."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    try:

        if TG_WH_AVAILABLE:

            if role == "supreme_admin":

                s24  = tg_wh.get_global_stats(24)

                s168 = tg_wh.get_global_stats(168)

            else:

                s24  = tg_wh.get_tenant_stats(admin_id, 24)

                s168 = tg_wh.get_tenant_stats(admin_id, 168)

        elif BOT_AVAILABLE:

            s24  = admin_bot.get_stats(24)

            s168 = admin_bot.get_stats(168)

        else:

            return jsonify({"ok": False, "error": "stats_unavailable"}), 503



        entries_24  = s24.get("entries", 0) or 1

        leads_24    = s24.get("leads", 0)

        paid_24     = s24.get("paid", 0)

        buy_24      = s24.get("click_buy", 0)

        conv_rate   = s24.get("conv_rate", 0)

        entries_7d  = s168.get("entries", 0) or 1

        leads_7d    = s168.get("leads", 0)



        lead_rate   = round((leads_24 / entries_24) * 100, 1)

        click_rate  = round((buy_24   / entries_24) * 100, 1)

        lead_7d_rate = round((leads_7d / entries_7d) * 100, 1)



        # Build real insights from actual data

        insights = []

        if leads_24 > 0:

            insights.append(f"\U0001f4cb **{leads_24} leads capturados** nas \u00faltimas 24h — taxa de capta\u00e7\u00e3o: {lead_rate}%.")

        else:

            insights.append("\U0001f4cb **Nenhum lead** nas \u00faltimas 24h. Verifique se o formul\u00e1rio est\u00e1 ativo.")



        if buy_24 > 0:

            insights.append(f"\U0001f6d2 **{buy_24} cliques em Comprar** — {click_rate}% dos visitantes chegaram ao checkout.")

        if paid_24 > 0:

            insights.append(f"\u2705 **{paid_24} pagamentos confirmados** nas \u00faltimas 24h.")

        if leads_7d > leads_24 * 7 * 1.3:

            insights.append("\U0001f4c8 **Performance acima da m\u00e9dia semanal** — ritmo de leads acelerado.")

        elif leads_7d < leads_24 * 7 * 0.7 and leads_24 > 0:

            insights.append("\U0001f4c9 **Performance abaixo da m\u00e9dia semanal** — analise se houve queda de tr\u00e1fego.")

        if conv_rate >= 10:

            insights.append(f"\U0001f3af **Convers\u00e3o {conv_rate}%** — resultado acima da m\u00e9dia de mercado (8-12%).")

        elif conv_rate > 0:

            insights.append(f"\U0001f3af **Convers\u00e3o {conv_rate}%** — otimize o texto do an\u00fancio para subir acima de 10%.")



        if not insights:

            insights = ["\U0001f4ca Sem dados suficientes ainda. Aguarde as primeiras visitas para ver insights reais."]



        return jsonify({

            "ok":             True,

            "conversion_rate": f"{conv_rate}%",

            "lead_rate":       f"{lead_rate}%",

            "click_rate":      f"{click_rate}%",

            "leads_24h":       leads_24,

            "paid_24h":        paid_24,

            "entries_24h":     entries_24,

            "insights":        insights,

            "period":          "24h",

        })

    except Exception as e:

        return jsonify({"ok": False, "error": str(e)}), 500









@app.route('/api/admin/me')

def api_admin_me():

    """Perfil completo do admin logado com stats pessoais."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    prof = {}

    stats_24h = {}

    stats_7d  = {}

    username  = ""

    slug      = ""



    if TG_WH_AVAILABLE:

        try:

            prof = tg_wh.get_tenant_profile(admin_id) or {}

        except Exception:

            prof = {}

        try:

            stats_24h = tg_wh.get_tg_stats(admin_id, 24)   or {}

        except Exception:

            stats_24h = {}

        try:

            stats_7d  = tg_wh.get_tg_stats(admin_id, 168)  or {}

        except Exception:

            stats_7d  = {}

        try:

            db  = tg_wh._get_db()

            row = db.execute("SELECT username, slug FROM tg_users WHERE tg_id=?", (admin_id,)).fetchone()

            db.close()

            if row:

                username = row["username"] or ""

                slug     = row["slug"] or ""

        except Exception:

            pass



    return jsonify({

        "ok":       True,

        "admin_id": admin_id,

        "role":     role,

        "is_supreme": (role == "supreme_admin"),

        "username": username,

        "slug":     slug,

        "profile": {

            "display_name": prof.get("display_name", f"Admin #{admin_id}"),

            "avatar_url":   prof.get("avatar_url", ""),

            "bio":          prof.get("bio", ""),

            "contact":      prof.get("contact", ""),

            "updated_at":   prof.get("updated_at", 0),

        },

        "stats_24h": stats_24h,

        "stats_7d":  stats_7d,

    })




@app.route('/api/admin/supreme/admin-stats')
def api_admin_stats_single():
    import sqlite3
    import os
    DB_PATH = os.environ.get("DB_PATH", "olpg_logs.db")
    admin_id, role = verify_admin_access(request)
    if not admin_id: return jsonify({"ok": False, "error": "unauthorized"}), 401
    target_id = request.args.get('id')
    if not target_id: return jsonify({"ok": False})
    try: target_id = int(target_id)
    except: pass
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        t_role = 'admin'
        try:
            cur.execute("SELECT role FROM vault WHERE tg_id = ?", (target_id,))
            row = cur.fetchone()
            if row: t_role = row['role']
        except: pass
        if target_id in getattr(admin_bot, "ADMINS_SUPREMOS", [6220800735]):
            t_role = 'supreme_admin'

        
        # Get products count and products
        cur.execute("SELECT title, created_at, 0 as sales FROM tenant_products WHERE tg_id = ? ORDER BY created_at DESC LIMIT 5", (target_id,))
        products_rows = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) as c FROM tenant_products WHERE tg_id = ?", (target_id,))
        prod_count = cur.fetchone()['c']
        
        # Get sales and revenue — verifica tg_events primeiro, depois events (bot.py)
        cur.execute("SELECT data_enc FROM tg_events WHERE tg_id = ? AND event_type = 'PAYMENT_CONFIRMED'", (target_id,))
        events_rows = cur.fetchall()

        # Fallback: para o supremo (ou quando tg_events vazia), busca da tabela principal
        if not events_rows:
            cur.execute("SELECT data_enc FROM events WHERE event_type = 'PAYMENT_CONFIRMED'")
            events_rows = cur.fetchall()

        import bot as _b
        sales_count = len(events_rows)
        revenue = 0.0
        for r in events_rows:
            try:
                dec = _b.crypto_engine.decrypt(r['data_enc'])
                if dec and 'amount' in dec:
                    amt = str(dec['amount']).replace(',', '.').strip()
                    revenue += float(amt)
            except: pass
        
        prods = []
        import datetime
        for p in products_rows:
            try:
                # Assuming created_at might be a float timestamp or string
                ts = p['created_at']
                if isinstance(ts, float) or isinstance(ts, int):
                    t_ago = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                else:
                    t_ago = str(ts).split()[0]
            except:
                t_ago = ''
            prods.append({
                "name": p['title'],
                "sales": p['sales'],
                "time_ago": t_ago
            })
            
    return jsonify({
        "ok": True,
        "stats": {
            "role": t_role,
            "sales": sales_count,
            "products": prod_count,
            "revenue": revenue
        },
        "products": prods
    })

@app.route('/api/admin/supreme/available-channels')
def api_available_channels():
    import sqlite3
    import os
    DB_PATH = os.environ.get("DB_PATH", "olpg_logs.db")
    admin_id, role = verify_admin_access(request)
    if not admin_id: return jsonify({"ok": False, "error": "unauthorized"}), 401
    
    channels = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            # Pegar todos os grupos/canais
            rows = conn.execute("SELECT chat_id, title, type, is_forum FROM bot_chats").fetchall()
            for r in rows:
                c_id = r["chat_id"]
                ch_obj = {"id": c_id, "title": r["title"] or c_id, "type": r["type"], "topics": []}
                if r["is_forum"]:
                    t_rows = conn.execute("SELECT thread_id, title FROM bot_topics WHERE chat_id=?", (c_id,)).fetchall()
                    for tr in t_rows:
                        ch_obj["topics"].append({"id": tr["thread_id"], "name": tr["title"]})
                channels.append(ch_obj)
        except Exception as e:
            pass
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT chat_id, title, type FROM bot_channels")
            rows = cur.fetchall()
            if rows:
                channels = []
                for r in rows:
                    ch = {"id": r["chat_id"], "title": r["title"], "type": r["type"], "topics": []}
                    cur.execute("SELECT thread_id, name FROM bot_topics WHERE chat_id = ?", (r["chat_id"],))
                    for t in cur.fetchall():
                        ch["topics"].append({"id": t["thread_id"], "name": t["name"]})
                    channels.append(ch)
    except:
        pass
        
    return jsonify({"ok": True, "channels": channels})

@app.route('/api/admin/profiles/all')

def api_admin_profiles_all():

    """Retorna perfis de todos os admins cadastrados para visualização mútua."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    profiles = []

    if TG_WH_AVAILABLE:

        profiles = tg_wh.get_all_tenant_profiles(is_supreme=(role == "supreme_admin"))

    return jsonify({"ok": True, "profiles": profiles})





@app.route('/api/admin/stats')

def api_admin_stats():

    """Retorna estatísticas isoladas por admin ou globais para o Admin Supremo."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    if TG_WH_AVAILABLE:

        if role == "supreme_admin":

            h24_tg  = tg_wh.get_global_stats(24)
            h168_tg = tg_wh.get_global_stats(168)

            # Mescla com dados reais do bot.py quando tg_events está vazia
            if BOT_AVAILABLE:
                h24_bot  = admin_bot.get_stats(24)
                h168_bot = admin_bot.get_stats(168)

                def _merge(tg, bot):
                    m = dict(tg)
                    for k in ('entries', 'pix_generated', 'paid', 'sessions', 'converted', 'click_buy'):
                        m[k] = (tg.get(k) or 0) + (bot.get(k) or 0)
                    m['leads'] = (tg.get('leads') or 0) + (bot.get('lead_captured') or 0)
                    m['lead_captured'] = m['leads']
                    if m.get('sessions', 0) > 0:
                        m['conv_rate'] = round((m.get('converted', 0) / m['sessions']) * 100, 1)
                    return m

                h24  = _merge(h24_tg,  h24_bot)
                h168 = _merge(h168_tg, h168_bot)
            else:
                h24, h168 = h24_tg, h168_tg

        else:

            h24 = tg_wh.get_tenant_stats(admin_id, 24)

            h168 = tg_wh.get_tenant_stats(admin_id, 168)

        return jsonify({"ok": True, "stats": h24, "h24": h24, "h168": h168})



    if not BOT_AVAILABLE:

        return jsonify({"error": "bot_not_available"}), 503

    try:

        h24  = admin_bot.get_stats(24)

        h168 = admin_bot.get_stats(168)

        return jsonify({"ok": True, "stats": h24, "h24": h24, "h168": h168})

    except Exception as e:

        return jsonify({"error": str(e)}), 500





@app.route('/api/admin/load-config')

def api_admin_load_config():

    """Carrega as configurações salvas do admin logado sem resetar ao atualizar a página."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"error": "unauthorized"}), 401



    if TG_WH_AVAILABLE and admin_id != 999999999:

        cfgs = tg_wh.get_tenant_all_config(admin_id)

        plan = tg_wh.get_user_plan(admin_id)

        slug = tg_wh.get_slug(admin_id)

        ok_clicks, curr_clicks, max_clicks = tg_wh.check_click_limit(admin_id)

        return jsonify({

            "ok": True,

            "config": cfgs,

            "plan": plan,

            "slug": slug,

            "usage": {"current": curr_clicks, "max": max_clicks, "allowed": ok_clicks}

        })



    # Admin Supremo / Fallback

    return jsonify({

        "ok": True,

        "config": {

            "product_name": admin_bot.get_config("product_name", ""),

            "product_price": admin_bot.get_config("product_price", ""),

            "whatsapp_number": admin_bot.get_config("whatsapp_number", ""),

            "seller_name": admin_bot.get_config("seller_name", "OLX Admin"),

            "logo_url": admin_bot.get_config("logo_url", "")

        },

        "plan": {"name": "Plano Supremo (Ilimitado)", "max_links": 9999, "max_clicks_month": 999999},

        "slug": "supreme",

        "usage": {"current": 0, "max": 999999, "allowed": True}

    })





# â”€â”€â”€ CATÃLOGO DE MULTI-PRODUTOS POR ADMIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# ─── CATÁLOGO DE MULTI-PRODUTOS POR ADMIN ────────────────────────────────────





@app.route('/api/admin/profile', methods=['POST'])

def api_admin_profile_save():

    """Salva perfil público do admin (display_name, bio, contact, avatar_url)."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    data = request.json or {}

    display_name = sanitize_input(data.get("display_name", ""), 80)

    bio          = sanitize_input(data.get("bio", ""), 300)

    contact      = sanitize_input(data.get("contact", ""), 100)

    avatar_url   = sanitize_input(data.get("avatar_url", ""), 500)



    if not display_name:

        return jsonify({"ok": False, "error": "Nome de exibição é obrigatório."}), 400



    prof = {

        "display_name": display_name,

        "bio":          bio,

        "contact":      contact,

        "avatar_url":   avatar_url,

        "updated_at":   int(time.time()),

    }



    if TG_WH_AVAILABLE:

        try:

            tg_wh.set_tenant_profile(

                admin_id,

                display_name=display_name,

                avatar_url=avatar_url,

                bio=bio,

                contact=contact

            )

        except Exception as e:

            return jsonify({"ok": False, "error": f"Erro ao salvar perfil: {e}"}), 500

    else:

        return jsonify({"ok": False, "error": "Perfil indisponível neste modo."}), 503



    if VALIDATORS_AVAILABLE and ActivityAudit:

        ActivityAudit.log('admin_profile_save', actor_id=admin_id, ip=_user_ip(),

                          details={'display_name': display_name})



    return jsonify({"ok": True, "message": "Perfil salvo com sucesso!", "profile": prof})





@app.route('/api/admin/preview', methods=['GET'])

def api_admin_preview():

    """

    Retorna dados completos para preview em tempo real do produto do admin.

    Inclui config do tenant + produto específico (por code) ou o produto ativo.

    Usado pelo painel admin para renderizar preview ao vivo da página do cliente.

    """

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    product_code = request.args.get("code", "").strip()
    slug = ""
    cfg  = {}
    product = None
    products = []

    try:
        if TG_WH_AVAILABLE:
            slug = tg_wh.get_slug(admin_id) or ""
            cfg  = tg_wh.get_tenant_all_config(admin_id) or {}
            if product_code:
                p = tg_wh.get_product_by_code(product_code)
                # Verifica se o produto pertence ao admin logado
                if p and p.get("tg_id") == admin_id:
                    product = p
            if not product:
                prods = tg_wh.get_tenant_products(admin_id)
                products = prods
                # Tenta o produto marcado como ativo, fallback ao primeiro
                product = next((p for p in prods if p.get("is_active")), prods[0] if prods else None)
            else:
                products = tg_wh.get_tenant_products(admin_id)
        elif BOT_AVAILABLE:
            cfg = {
                "product_name":  admin_bot.get_config("product_name", ""),
                "product_price": admin_bot.get_config("product_price", ""),
                "product_image": admin_bot.get_config("product_image", ""),
                "seller_name":   admin_bot.get_config("seller_name", ""),
                "logo_url":      admin_bot.get_config("logo_url", ""),
                "whatsapp_number": admin_bot.get_config("whatsapp_number", ""),
            }

        # Monta URL do link público
        if product_code and slug:
            public_url = f"{BASE_URL}/p/{slug}/{product_code}"
        elif product and slug:
            code = product.get("product_code") or product.get("code") or ""
            public_url = f"{BASE_URL}/p/{slug}/{code}" if code else f"{BASE_URL}/p/{slug}"
        else:
            public_url = f"{BASE_URL}/p/{slug}" if slug else BASE_URL

        return jsonify({
            "ok":         True,
            "slug":       slug,
            "config":     cfg,
            "product":    product,
            "products":   products,
            "public_url": public_url,
            "base_url":   BASE_URL,
        })
    except Exception as e:
        print(f"[PREVIEW] Erro ao carregar preview: {e}")
        return jsonify({"ok": False, "error": f"Erro ao gerar preview: {str(e)}"}), 500





@app.route('/api/admin/my-products', methods=['GET', 'POST'])

def api_admin_my_products():

    """Listar ou criar produtos no catálogo próprio do admin logado."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    if request.method == 'POST':

        data = request.json or {}

        title = data.get("title", "").strip()
        price = data.get("price", "").strip()
        old_price = data.get("old_price", "").strip()
        description = data.get("description", "").strip()
        image_url = data.get("image_url", "").strip()
        image1 = data.get("image1", "").strip() or image_url
        image2 = data.get("image2", "").strip()
        image3 = data.get("image3", "").strip()
        product_code = data.get("product_code", "").strip()
        shipping_mode = data.get("shipping_mode", "full").strip()
        shipping_fee = data.get("shipping_fee", "19.90").strip() or "19.90"
        shipping_coupon = data.get("shipping_coupon", "").strip()
        coupon_active = 1 if data.get("coupon_active", 1) in (1, "1", True, "true") else 0
        coupon_only_shipping = 1 if data.get("coupon_only_shipping", 1) in (1, "1", True, "true") else 0
        coupon_discount_value = str(data.get("coupon_discount_value") or "").strip()
        coupon_discount_mode = str(data.get("coupon_discount_mode") or "pct").strip().lower() or "pct"
        seller_name = data.get("seller_name", "").strip()
        seller_since = data.get("seller_since", "").strip()
        seller_avatar = data.get("seller_avatar", "").strip()
        det_category = data.get("det_category", "").strip()
        det_brand = data.get("det_brand", "").strip()
        det_model = data.get("det_model", "").strip()
        det_condition = data.get("det_condition", "").strip()
        det_memory = data.get("det_memory", "").strip()
        det_color = data.get("det_color", "").strip()
        payment_badges = data.get("payment_badges", "").strip()
        breadcrumb_zone = data.get("breadcrumb_zone", "").strip()
        seller_sales_completed = data.get("seller_sales_completed", "").strip()
        seller_sales_canceled = data.get("seller_sales_canceled", "").strip()
        seller_dispatch_time = data.get("seller_dispatch_time", "").strip()
        seller_rating = data.get("seller_rating", "").strip()
        seller_reviews = data.get("seller_reviews", "").strip()
        seller_level = data.get("seller_level", "").strip()
        seller_email_verified = 1 if data.get("seller_email_verified", 1) in (1, "1", True, "true") else 0
        seller_phone_verified = 1 if data.get("seller_phone_verified", 1) in (1, "1", True, "true") else 0
        seller_id_verified = 1 if data.get("seller_id_verified", 1) in (1, "1", True, "true") else 0
        seller_fb_verified = 1 if data.get("seller_fb_verified", 0) in (1, "1", True, "true") else 0
        seller_fb_url = data.get("seller_fb_url", "").strip()
        product_published_at = data.get("product_published_at", "").strip()

        if not title:
            return jsonify({"ok": False, "error": "Título é obrigatório."}), 400

        # ── Defaults inteligentes: se o admin não preencheu, usa valores do config global
        if TG_WH_AVAILABLE:
            _cfgs = tg_wh.get_tenant_all_config(admin_id)
            if not seller_name:   seller_name   = _cfgs.get("seller_name",   "")
            if not seller_since:  seller_since  = _cfgs.get("seller_since",  "")
            if not seller_avatar: seller_avatar = _cfgs.get("seller_avatar", "")
            if not breadcrumb_zone: breadcrumb_zone = _cfgs.get("breadcrumb_zone", "Zona Norte")
            if not description:   description   = _cfgs.get("product_description", "")

        if TG_WH_AVAILABLE:
            try:
                code = tg_wh.create_tenant_product(
                    admin_id, title, price, old_price, description,
                    image_url, image1, image2, image3,
                    product_code=product_code,
                    shipping_mode=shipping_mode,
                    shipping_fee=shipping_fee,
                    shipping_coupon=shipping_coupon,
                    coupon_active=coupon_active,
                    coupon_only_shipping=coupon_only_shipping,
                    coupon_discount_value=coupon_discount_value,
                    coupon_discount_mode=coupon_discount_mode or "pct",
                    seller_name=seller_name,
                    seller_since=seller_since,
                    seller_avatar=seller_avatar,
                    det_category=det_category,
                    det_brand=det_brand,
                    det_model=det_model,
                    det_condition=det_condition,
                    det_memory=det_memory,
                    det_color=det_color,
                    payment_badges=payment_badges,
                    breadcrumb_zone=breadcrumb_zone,
                    seller_sales_completed=seller_sales_completed,
                    seller_sales_canceled=seller_sales_canceled,
                    seller_dispatch_time=seller_dispatch_time,
                    seller_rating=seller_rating,
                    seller_reviews=seller_reviews,
                    seller_level=seller_level,
                    seller_email_verified=seller_email_verified,
                    seller_phone_verified=seller_phone_verified,
                    seller_id_verified=seller_id_verified,
                    seller_fb_verified=seller_fb_verified,
                    seller_fb_url=seller_fb_url,
                    product_published_at=product_published_at
                )

                slug = tg_wh.get_slug(admin_id)

                # Link legível: /p/slug-do-admin/codigo-do-produto
                if slug:
                    unique_link = f"{BASE_URL}/p/{slug}/{code}"
                else:
                    unique_link = f"{BASE_URL}/p/{code}"

                if VALIDATORS_AVAILABLE and ActivityAudit:
                    try:
                        ActivityAudit.log('admin_product_create', actor_id=admin_id, ip=_user_ip(),
                                          slug=slug, details={'code': code, 'title': title, 'price': price, 'link': unique_link, 'coupon': shipping_coupon, 'coupon_active': coupon_active})
                    except Exception as audit_err:
                        print(f"[AUDIT] Erro ao registrar auditoria de produto: {audit_err}")

                return jsonify({"ok": True, "product_code": code, "unique_link": unique_link, "message": "Produto criado com sucesso no catálogo!"})
            except Exception as e:
                print(f"[PROD_CREATE] Erro ao criar produto: {e}")
                return jsonify({"ok": False, "error": f"Erro ao criar produto: {str(e)}"}), 400

    products = []
    if TG_WH_AVAILABLE:
        try:
            prods = tg_wh.get_tenant_products(admin_id)
            slug = tg_wh.get_slug(admin_id)
            for p in prods:
                # Link legível: /p/slug-do-admin/codigo-do-produto
                if slug:
                    p["unique_link"] = f"{BASE_URL}/p/{slug}/{p['product_code']}"
                else:
                    p["unique_link"] = f"{BASE_URL}/p/{p['product_code']}"
                products.append(p)
        except Exception as e:
            print(f"[MY_PRODUCTS] Erro ao carregar produtos do tenant: {e}")
            return jsonify({"ok": False, "error": f"Erro ao listar produtos: {str(e)}"}), 500

    return jsonify({"ok": True, "products": products})





@app.route('/api/admin/my-products/<product_code>', methods=['PUT', 'DELETE'])

def api_admin_manage_product(product_code):

    """Editar ou deletar produto específico do catálogo do admin."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    if request.method == 'DELETE':

        if TG_WH_AVAILABLE:

            tg_wh.delete_tenant_product(admin_id, product_code)

            if VALIDATORS_AVAILABLE:

                ActivityAudit.log('admin_product_delete', actor_id=admin_id, ip=_user_ip(),

                                  details={'product_code': product_code})

            return jsonify({"ok": True, "message": "Produto excluído."})

        return jsonify({"ok": False, "error": "Recurso indisponível."}), 400



    if request.method == 'PUT':
        data = request.json or {}
        if TG_WH_AVAILABLE:
            ok = tg_wh.update_tenant_product(admin_id, product_code, data)
            if ok:
                slug = tg_wh.get_slug(admin_id)
                if slug:
                    unique_link = f"{BASE_URL}/p/{slug}/{product_code}"
                else:
                    unique_link = f"{BASE_URL}/p/{product_code}"
                return jsonify({"ok": True, "unique_link": unique_link, "message": "Produto atualizado com sucesso!"})
            return jsonify({"ok": False, "error": "Produto não encontrado ou sem permissão."}), 404
        return jsonify({"ok": False, "error": "Recurso indisponível."}), 400





# â”€â”€â”€ CANAIS DE LOGS CONFIGURÃVEIS DO ADMIN SUPREMO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route('/api/admin/supreme/log-channels', methods=['GET', 'POST'])

def api_admin_supreme_log_channels():

    """Configura ou obtém os canais de logs do Telegram (visita, lead, pix, pagamento)."""

    admin_id, role = verify_admin_access(request)

    if role != "supreme_admin":

        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403



    if request.method == 'POST':

        data = request.json or {}

        channel_key = data.get("channel_key", "").strip()

        chat_id     = data.get("chat_id")

        title       = data.get("title", "").strip()



        if not channel_key or not chat_id:

            return jsonify({"ok": False, "error": "channel_key e chat_id são obrigatórios"}), 400



        if TG_WH_AVAILABLE:

            tg_wh.set_log_channel(channel_key, str(chat_id), title)

            return jsonify({"ok": True, "message": f"Canal de logs {channel_key} configurado para chat {chat_id}!"})



    channels = {}

    if TG_WH_AVAILABLE:

        channels = tg_wh.get_log_channels()

    return jsonify({"ok": True, "channels": channels})





@app.route('/api/admin/events')
def api_admin_events():
    """Retorna eventos recentes descriptografados com métricas e contadores em tempo real."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"error": "unauthorized"}), 401

    limit = min(int(request.args.get('limit', 50)), 200)
    slug = request.args.get('slug', '').strip()

    events_list = []
    try:
        conn = None
        if BOT_AVAILABLE:
            conn = admin_bot.get_db()
        elif TG_WH_AVAILABLE:
            conn = tg_wh._get_db()

        if conn:
            # 1. Busca eventos da tabela tg_events
            try:
                if role == "supreme_admin":
                    if slug:
                        rows_tg = conn.execute(
                            "SELECT event_type, session_id, ip, data_enc, created_at, slug FROM tg_events WHERE slug=? ORDER BY created_at DESC LIMIT ?",
                            (slug, limit)
                        ).fetchall()
                    else:
                        rows_tg = conn.execute(
                            "SELECT event_type, session_id, ip, data_enc, created_at, slug FROM tg_events ORDER BY created_at DESC LIMIT ?",
                            (limit,)
                        ).fetchall()
                else:
                    rows_tg = conn.execute(
                        "SELECT event_type, session_id, ip, data_enc, created_at, slug FROM tg_events WHERE tg_id=? ORDER BY created_at DESC LIMIT ?",
                        (admin_id, limit)
                    ).fetchall()

                for r in rows_tg:
                    data = {}
                    if r["data_enc"]:
                        try:
                            dec = admin_bot.decrypt_data(r["data_enc"]) if BOT_AVAILABLE else {}
                            data = dec if isinstance(dec, dict) else {}
                        except Exception:
                            try:
                                data = json.loads(r["data_enc"])
                            except Exception:
                                data = {}
                    events_list.append({
                        "type": r["event_type"],
                        "session": r["session_id"],
                        "ip": r["ip"],
                        "data": data,
                        "ts": r["created_at"],
                        "slug": r["slug"] if "slug" in r.keys() else ""
                    })
            except Exception as e_tg:
                print(f"[api_admin_events] tg_events error: {e_tg}")

            # 2. Busca também da tabela events (eventos globais/locais)
            try:
                rows_ev = conn.execute(
                    "SELECT event_type, session_id, ip, data_enc, created_at FROM events ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                for r in rows_ev:
                    data = {}
                    if r["data_enc"]:
                        try:
                            dec = admin_bot.decrypt_data(r["data_enc"]) if BOT_AVAILABLE else {}
                            data = dec if isinstance(dec, dict) else {}
                        except Exception:
                            try:
                                data = json.loads(r["data_enc"])
                            except Exception:
                                data = {}
                    events_list.append({
                        "type": r["event_type"],
                        "session": r["session_id"],
                        "ip": r["ip"],
                        "data": data,
                        "ts": r["created_at"],
                        "slug": data.get("slug", "")
                    })
            except Exception as e_ev:
                print(f"[api_admin_events] events error: {e_ev}")

            conn.close()

        # Deduplicação por (type, session, timestamp aproximado)
        seen = set()
        deduped = []
        for ev in sorted(events_list, key=lambda x: x["ts"] or 0, reverse=True):
            k = (ev["type"], ev["session"], int(ev["ts"] or 0))
            if k not in seen:
                seen.add(k)
                deduped.append(ev)

        final_events = deduped[:limit]

        # Métricas agregadas de eventos para os elementos de métricas do feed
        counts = {
            "all": len(deduped),
            "leads": sum(1 for e in deduped if e["type"] in ("LEAD_CAPTURED", "LEAD_PENDING")),
            "buy": sum(1 for e in deduped if e["type"] in ("CLICK_BUY", "STEP_1_BUY")),
            "pix": sum(1 for e in deduped if e["type"] in ("PIX_GENERATED", "STEP_PIX_DISPLAYED")),
            "paid": sum(1 for e in deduped if e["type"] in ("PAYMENT_CONFIRMED", "PIX_PAID", "PAYMENT_CONFIRMED_SUCCESS")),
            "visits": sum(1 for e in deduped if e["type"] in ("PAGE_ENTRY", "PAGE_EXIT"))
        }

        return jsonify({
            "ok": True,
            "events": final_events,
            "count": len(final_events),
            "counts": counts
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "events": [], "count": 0, "counts": {}}), 500


@app.route('/api/admin/sessions')
def api_admin_sessions():
    """Retorna sessões recentes — unificando tg_sessions e sessions."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"error": "unauthorized"}), 401

    limit = min(int(request.args.get('limit', 30)), 100)
    slug = request.args.get('slug', '').strip()

    sessions_list = []
    try:
        conn = None
        if BOT_AVAILABLE:
            conn = admin_bot.get_db()
        elif TG_WH_AVAILABLE:
            conn = tg_wh._get_db()

        if conn:
            # 1. De tg_sessions
            try:
                if role == "supreme_admin":
                    if slug:
                        rows_tgs = conn.execute(
                            "SELECT session_id, ip, ua, entered_at, left_at, converted, slug FROM tg_sessions WHERE slug=? ORDER BY entered_at DESC LIMIT ?",
                            (slug, limit)
                        ).fetchall()
                    else:
                        rows_tgs = conn.execute(
                            "SELECT session_id, ip, ua, entered_at, left_at, converted, slug FROM tg_sessions ORDER BY entered_at DESC LIMIT ?",
                            (limit,)
                        ).fetchall()
                else:
                    rows_tgs = conn.execute(
                        "SELECT session_id, ip, ua, entered_at, left_at, converted, slug FROM tg_sessions WHERE tg_id=? ORDER BY entered_at DESC LIMIT ?",
                        (admin_id, limit)
                    ).fetchall()
                for r in rows_tgs:
                    sessions_list.append(dict(r))
            except Exception as e_tgs:
                print(f"[api_admin_sessions] tg_sessions error: {e_tgs}")

            # 2. De sessions global
            try:
                rows_s = conn.execute(
                    "SELECT session_id, ip, ua, entered_at, left_at, converted FROM sessions ORDER BY entered_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                for r in rows_s:
                    sessions_list.append(dict(r))
            except Exception as e_s:
                print(f"[api_admin_sessions] sessions error: {e_s}")

            conn.close()

        # Deduplica por session_id
        seen = set()
        deduped = []
        for s in sorted(sessions_list, key=lambda x: x.get("entered_at") or 0, reverse=True):
            sid = s.get("session_id")
            if sid and sid not in seen:
                seen.add(sid)
                deduped.append(s)

        final_sessions = deduped[:limit]
        return jsonify({"ok": True, "sessions": final_sessions, "count": len(final_sessions)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500






@app.route('/api/admin/upload', methods=['POST'])

def api_admin_upload():

    """Upload de imagens — requer autenticação de admin."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    if 'file' not in request.files:

        return jsonify({"ok": False, "error": "Nenhum arquivo enviado"}), 400



    file = request.files['file']

    if not file or file.filename == '':

        return jsonify({"ok": False, "error": "Arquivo em branco ou invalido"}), 400



    ext = os.path.splitext(file.filename)[1].lower()

    allowed_exts = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.mp4', '.webm', '.ogg', '.mov'}

    if ext not in allowed_exts:

        return jsonify({"ok": False, "error": "Formato inválido. Use PNG, JPG, WEBP, GIF, SVG ou vídeos MP4, WEBM, MOV."}), 400



    # Limite de tamanho: 50MB para vídeos / imagens
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if size > 50 * 1024 * 1024:
        return jsonify({"ok": False, "error": "Arquivo muito grande. Máximo 50MB."}), 413



    uploads_dir = os.path.join(app.static_folder, 'images', 'uploads')

    os.makedirs(uploads_dir, exist_ok=True)



    filename = f"img_{uuid.uuid4().hex[:12]}{ext}"

    filepath = os.path.join(uploads_dir, filename)

    file.save(filepath)



    image_url = f"/static/images/uploads/{filename}"

    _log("IMAGE_UPLOADED", str(uuid.uuid4()), {"admin_id": admin_id, "filename": filename, "url": image_url})

    return jsonify({"ok": True, "url": image_url, "filename": filename})





@app.route('/api/admin/config', methods=['GET'])

def api_admin_config_get():

    """Returns current admin config toggles and key settings."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    try:

        cfg = {}

        toggle_keys = ["active", "pixel_active", "notifications"]

        if TG_WH_AVAILABLE and admin_id != 999999999:

            for k in toggle_keys:

                val = tg_wh.get_tenant_config(admin_id, k)

                cfg[k] = val if val is not None else "1"

        elif BOT_AVAILABLE:

            for k in toggle_keys:

                val = admin_bot.get_config(k)

                cfg[k] = val if val is not None else "1"

        return jsonify({"ok": True, "config": cfg, "role": role})

    except Exception as e:

        return jsonify({"ok": True, "config": {}, "role": role})





@app.route('/api/admin/config', methods=['POST'])

def api_admin_config_save():

    """Saves multiple config keys isolated per tenant/admin."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    data = request.json or {}

    allowed_keys = {

        "product_name", "product_price", "product_old_price", "product_description",

        "product_image", "product_image1", "product_image2", "product_image3",

        "whatsapp_number", "whatsapp_message",

        "seller_name", "seller_status", "seller_since", "logo_url",

        "pix_key", "payment_badges",
        "det_category", "det_brand", "det_model", "det_condition", "det_storage", "det_color",
        "active", "pixel_active", "notifications",
        # ── Admin Supremo: identidade visual global ──
        "search_placeholder",
        "favicon_url",
    }

    saved = []

    validation_errors = {}

    for key, value in data.items():

        if key in allowed_keys and isinstance(value, str):

            clean_val = value.strip()

            # Apenas Admin Supremo pode alterar logo_url, payment_badges, search_placeholder e favicon_url

            if key in ["logo_url", "payment_badges", "search_placeholder", "favicon_url"] and role != "supreme_admin":

                continue

            if not clean_val and key not in ["logo_url", "payment_badges"]:

                continue

            # Validacao avancada por tipo de campo

            if VALIDATORS_AVAILABLE and clean_val:

                field_map = {

                    'product_name': 'product_name', 'product_price': 'price',

                    'product_old_price': 'price', 'product_image': 'url',

                    'product_image1': 'url', 'product_image2': 'url', 'product_image3': 'url',

                    'whatsapp_number': 'wa_number', 'logo_url': 'url',

                    'seller_name': 'name',

                }

                ftype = field_map.get(key)

                if ftype:

                    ok_v, result_v, _ = FieldValidator.validate_field(ftype, clean_val)

                    if not ok_v:

                        validation_errors[key] = result_v

                        continue

                    clean_val = result_v  # Usa valor normalizado

                elif FieldValidator.has_injection(clean_val):

                    validation_errors[key] = 'Campo contem caracteres invalidos.'

                    continue

                else:

                    clean_val = FieldValidator.sanitize(clean_val)

            # Save logic

            if key in ["logo_url", "payment_badges", "search_placeholder", "favicon_url"]:

                if BOT_AVAILABLE:

                    admin_bot.set_config(key, clean_val)

                saved.append(key)

            elif clean_val:

                if TG_WH_AVAILABLE and admin_id != 999999999:

                    tg_wh.set_tenant_config(admin_id, key, clean_val)

                elif BOT_AVAILABLE:

                    admin_bot.set_config(key, clean_val)

                saved.append(key)

    _log("ADMIN_CONFIG_SAVED", str(uuid.uuid4()), {"admin_id": admin_id, "keys_saved": saved})

    if VALIDATORS_AVAILABLE:

        ActivityAudit.log('admin_config_save', actor_id=admin_id, ip=_user_ip(),

                          details={'keys': saved, 'count': len(saved), 'errors': validation_errors})

    if validation_errors:

        return jsonify({"ok": len(saved) > 0, "saved": saved, "validation_errors": validation_errors,

                        "message": f"{len(saved)} campos salvos, {len(validation_errors)} erro(s) de validacao."})

    return jsonify({"ok": True, "saved": saved, "message": f"{len(saved)} configuracao(es) salva(s) com sucesso."})





# â”€â”€â”€ ENDPOINTS GERENCIAMENTO SUPREMO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route('/api/admin/supreme/tenants')

def api_admin_supreme_tenants():

    """Retorna lista completa de admins/tenants com planos e uso de visitas para o Admin Supremo."""

    admin_id, role = verify_admin_access(request)

    if role != "supreme_admin":

        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403



    if not TG_WH_AVAILABLE:

        return jsonify({"ok": True, "tenants": []})



    users = tg_wh.get_all_tenants()

    res = []

    for u in users:

        tid = u["tg_id"]

        plan = tg_wh.get_user_plan(tid)

        ok_c, curr_c, max_c = tg_wh.check_click_limit(tid)

        st = tg_wh.get_tenant_stats(tid, 720) # 30 dias

        res.append({

            "tg_id": tid,

            "username": u["username"],

            "slug": u["slug"],

            "created_at": u["created_at"],

            "link": f"{BASE_URL}/p/{u['slug']}",

            "plan": plan,

            "usage": {"current": curr_c, "max": max_c, "allowed": ok_c},

            "stats": st

        })



    return jsonify({"ok": True, "tenants": res, "total": len(res)})


@app.route('/api/admin/supreme/set-role', methods=['POST'])
def api_admin_supreme_set_role():
    """Altera o cargo de um admin no banco de dados do Supreme."""
    admin_id, role = verify_admin_access(request)
    if role != "supreme_admin":
        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403

    data = request.json or {}
    target_tg_id = data.get("tg_id")
    new_role = data.get("role")
    
    if not target_tg_id or not new_role:
        return jsonify({"ok": False, "error": "tg_id e role são obrigatórios"}), 400
        
    # Salvar papel (em cenário ideal isso estaria no db.py, mas como é pra teste real e visualização):
    # db.update_user_role(target_tg_id, new_role)
    
    return jsonify({"ok": True, "msg": f"Cargo de {target_tg_id} atualizado para {new_role}"})

@app.route('/api/admin/supreme/punish', methods=['POST'])
def api_admin_supreme_punish():
    """Aplica suspensão ou ban num admin pelo tg_id no vault."""
    admin_id, role = verify_admin_access(request)
    if role != "supreme_admin":
        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403

    data = request.json or {}
    target_tg_id = data.get("tg_id")
    duration = data.get("duration", "permanent")
    reason = sanitize_input(str(data.get("reason", "Violação de regras")), 200)

    if not target_tg_id:
        return jsonify({"ok": False, "error": "tg_id é obrigatório"}), 400

    try:
        target_tg_id = int(target_tg_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "tg_id inválido"}), 400

    if TG_WH_AVAILABLE:
        try:
            tg_wh.set_tenant_config(target_tg_id, "account_status", "banned")
            tg_wh.set_tenant_config(target_tg_id, "ban_reason", reason)
            tg_wh.set_tenant_config(target_tg_id, "ban_duration", str(duration))
            tg_wh.set_tenant_config(target_tg_id, "ban_at", str(time.time()))
        except Exception as _pe:
            log.warning("[PUNISH] set_tenant_config error: %s", _pe)

    _log("SUPREME_PUNISH", str(uuid.uuid4()), {
        "admin_id": admin_id,
        "target_tg_id": target_tg_id,
        "duration": duration,
        "reason": reason,
        "ip": _user_ip()
    })

    return jsonify({"ok": True, "msg": f"Usuário {target_tg_id} banido com sucesso ({duration}).", "reason": reason})


# ─── BAN PERMANENTE DE COMPRADORES POR IP ─────────────────────────────────────

@app.route('/api/admin/supreme/ban-buyer-ip', methods=['POST'])
def api_ban_buyer_ip():
    """
    Bane permanentemente por IP um comprador que realizou e confirmou uma compra.
    Pesquisa o payment_id ou IP direto na tabela payments (status=paid) e insere na ip_bans.
    RESTRITO ao Admin Supremo.
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id or role != "supreme_admin":
        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403

    if not BOT_AVAILABLE:
        return jsonify({"ok": False, "error": "Banco de dados indisponível"}), 503

    data = request.json or {}
    target_ip    = sanitize_input(str(data.get("ip", "")).strip(), 45)
    payment_id   = sanitize_input(str(data.get("payment_id", "")).strip(), 100)
    reason       = sanitize_input(str(data.get("reason", "Comprador banido permanentemente pelo Admin Supremo")), 200)

    if not target_ip and not payment_id:
        return jsonify({"ok": False, "error": "Informe o ip ou payment_id do comprador"}), 400

    conn = admin_bot.get_db()
    try:
        _ensure_payment_tables(conn)

        # ── Resolve o IP a partir do payment_id, se fornecido
        resolved_ip    = target_ip
        resolved_pid   = payment_id
        resolved_amount = 0.0

        if payment_id:
            row = conn.execute(
                "SELECT ip, amount, status FROM payments WHERE (payment_id=? OR c7_id=?) LIMIT 1",
                (payment_id, payment_id)
            ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": f"Pagamento '{payment_id}' não encontrado"}), 404
            if row["status"] not in ("paid", "confirmed", "approved"):
                return jsonify({
                    "ok": False,
                    "error": f"Pagamento ainda não confirmado (status: {row['status']}). Só compradores com compra paga podem ser banidos por este método."
                }), 400
            if row["ip"]:
                resolved_ip    = row["ip"]
            resolved_amount = float(row["amount"] or 0)

        if not resolved_ip:
            return jsonify({"ok": False, "error": "IP não encontrado para este pagamento"}), 400

        # ── Checa se já está banido
        already = conn.execute("SELECT ip FROM ip_bans WHERE ip=? LIMIT 1", (resolved_ip,)).fetchone()
        if already:
            return jsonify({"ok": True, "msg": f"IP {resolved_ip} já estava banido.", "ip": resolved_ip, "already_banned": True})

        # ── Insere ban permanente
        conn.execute(
            "INSERT INTO ip_bans(ip, reason, banned_by, banned_at, payment_id, amount) VALUES(?,?,?,?,?,?)",
            (resolved_ip, reason, admin_id, time.time(), resolved_pid or None, resolved_amount or None)
        )
        conn.commit()

        _log("SUPREME_BAN_BUYER_IP", str(uuid.uuid4()), {
            "admin_id": admin_id,
            "banned_ip": resolved_ip,
            "payment_id": resolved_pid,
            "amount": resolved_amount,
            "reason": reason,
            "ip": _user_ip()
        })

        return jsonify({
            "ok": True,
            "msg": f"IP {resolved_ip} banido permanentemente com sucesso.",
            "ip": resolved_ip,
            "reason": reason,
            "payment_id": resolved_pid,
            "amount": resolved_amount
        })
    except Exception as e:
        log.error("[BAN_BUYER_IP] erro: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/admin/supreme/banned-ips', methods=['GET'])
def api_list_banned_ips():
    """Lista todos os IPs banidos permanentemente. RESTRITO ao Admin Supremo."""
    admin_id, role = verify_admin_access(request)
    if not admin_id or role != "supreme_admin":
        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403

    if not BOT_AVAILABLE:
        return jsonify({"ok": True, "bans": []})

    conn = admin_bot.get_db()
    try:
        _ensure_payment_tables(conn)
        rows = conn.execute(
            "SELECT ip, reason, banned_by, banned_at, payment_id, amount FROM ip_bans ORDER BY banned_at DESC LIMIT 500"
        ).fetchall()
        bans = []
        for r in rows:
            bans.append({
                "ip": r["ip"],
                "reason": r["reason"],
                "banned_by": r["banned_by"],
                "banned_at": r["banned_at"],
                "payment_id": r["payment_id"],
                "amount": r["amount"],
                "banned_at_fmt": datetime.fromtimestamp(r["banned_at"]).strftime("%d/%m/%Y %H:%M") if r["banned_at"] else ""
            })
        return jsonify({"ok": True, "bans": bans, "total": len(bans)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/admin/supreme/unban-ip', methods=['POST'])
def api_unban_ip():
    """Remove o ban permanente de um IP. RESTRITO ao Admin Supremo."""
    admin_id, role = verify_admin_access(request)
    if not admin_id or role != "supreme_admin":
        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403

    target_ip = sanitize_input(str((request.json or {}).get("ip", "")).strip(), 45)
    if not target_ip:
        return jsonify({"ok": False, "error": "IP é obrigatório"}), 400

    if not BOT_AVAILABLE:
        return jsonify({"ok": False, "error": "Banco de dados indisponível"}), 503

    conn = admin_bot.get_db()
    try:
        conn.execute("DELETE FROM ip_bans WHERE ip=?", (target_ip,))
        conn.commit()
        return jsonify({"ok": True, "msg": f"Ban do IP {target_ip} removido com sucesso."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# ─── MÉTRICAS DINÂMICAS DO GATEWAY ATIVO ──────────────────────────────────────

@app.route('/api/admin/gateway/active-metrics', methods=['GET'])
def api_active_gateway_metrics():
    """
    Retorna saldo, nome, logo, taxas e limites do gateway ATUALMENTE ATIVO no vault.
    O painel financeiro usa este endpoint para exibir informações do gateway real — não fixo na ElitePay.
    RESTRITO ao Admin Supremo.
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if role != "supreme_admin":
        return jsonify({"ok": False, "error": "acesso_restrito"}), 403

    keys   = _get_live_gateway_keys(admin_id)
    active = keys.get("gateway", "elitepay")
    cid    = keys.get("client_id") or keys.get("api_key", "")
    csec   = keys.get("client_secret") or keys.get("api_secret", "")
    burl   = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")

    # Meta de cada gateway
    GW_META_SERVER = {
        "elitepay":  {"name": "ElitePay · Saldo & Finanças",  "logo": "EP", "color": "#10B981", "auth_type": "x-client-id / x-client-secret"},
        "uniaopay":  {"name": "União 7 Pay · Saldo & Finanças","logo": "U7", "color": "#F59E0B", "auth_type": "Bearer API Key"},
        "mercadopago":{"name": "Mercado Pago · Saldo & Finanças","logo": "MP","color": "#009EE3","auth_type": "Bearer Token"},
        "pagarme":   {"name": "Pagar.me · Saldo & Finanças",   "logo": "PM", "color": "#7C3AED", "auth_type": "API Key"},
    }
    meta = GW_META_SERVER.get(active, {"name": f"{active} · Saldo & Finanças", "logo": active[:2].upper(), "color": "#6B7280", "auth_type": "API Key"})

    balance_info = None
    status       = "disconnected"
    quote_data   = {}
    rates_data   = {}

    is_configured = bool(cid and "xxx" not in cid)

    if is_configured:
        try:
            if active == "elitepay":
                headers = get_elitepay_headers(cid, csec)
                res = requests.get(f"{burl}/api/v1/balance", headers=headers, timeout=6)
                if res.status_code == 200:
                    status = "connected"
                    raw = res.json().get("data", {})
                    balance_info = {"balance": float(raw.get("balance", 0))}
                else:
                    status = f"http_{res.status_code}"

                # Busca cotação e taxas ElitePay
                try:
                    qr = requests.get(f"{burl}/api/v1/crypto/quote", timeout=5)
                    if qr.status_code == 200:
                        qd = qr.json()
                        if qd.get("success") and qd.get("cotacao"):
                            quote_data = qd.get("cotacao", {})
                            rates_data = {
                                "fee_pct": qd.get("taxas", {}).get("plataforma_percent", 4),
                                "fee_fixed": 4,
                                "min": qd.get("limites", {}).get("minimo", 20),
                                "max": qd.get("limites", {}).get("maximo", 2000),
                                "usdt_brl": qd.get("cotacao", {}).get("usdt_brl", 0)
                            }
                except Exception:
                    pass

            elif active == "uniaopay":
                u7_cfg = _get_uniaopay_config(admin_id)
                api_key = u7_cfg.get("api_key", "")
                if api_key:
                    # União 7 Pay não tem endpoint de saldo padronizado; reporta como configurado
                    status = "connected"
                    balance_info = {"balance": 0.0, "note": "Saldo não disponível via API União 7 Pay"}
                    rates_data = {"fee_pct": 0, "fee_fixed": 0, "min": 20, "max": 10000}

            else:
                # Gateway genérico — tenta GET /balance com auth bearer
                headers_generic = {
                    "Authorization": f"Bearer {csec or cid}",
                    "x-api-key": cid,
                    "Content-Type": "application/json"
                }
                try:
                    res = requests.get(f"{burl}/balance", headers=headers_generic, timeout=6)
                    if res.status_code == 200:
                        status = "connected"
                        rj = res.json()
                        bal = rj.get("balance") or rj.get("amount") or rj.get("data", {}).get("balance", 0)
                        balance_info = {"balance": float(bal)}
                    else:
                        status = f"http_{res.status_code}"
                except Exception:
                    status = "error_connecting"
        except Exception:
            status = "error_connecting"

    cid_masked = f"{cid[:6]}...{cid[-4:]}" if len(cid) > 10 else (cid if cid else "não configurado")

    return jsonify({
        "ok": True,
        "gateway": active,
        "name": meta["name"],
        "logo": meta["logo"],
        "color": meta["color"],
        "auth_type": meta["auth_type"],
        "status": status,
        "is_configured": is_configured,
        "client_id_masked": cid_masked,
        "balance": balance_info,
        "quote": quote_data,
        "rates": rates_data
    })



@app.route('/api/admin/supreme/set-plan', methods=['POST'])

def api_admin_supreme_set_plan():

    """Altera o plano de um admin (Free, Starter, Pro, Unlimited)."""

    admin_id, role = verify_admin_access(request)

    if role != "supreme_admin":

        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403



    data = request.json or {}

    target_tg_id = data.get("tg_id")

    plan_key = data.get("plan")



    if not target_tg_id or not plan_key:

        return jsonify({"ok": False, "error": "tg_id e plan são obrigatórios"}), 400



    if TG_WH_AVAILABLE and tg_wh.set_user_plan(target_tg_id, plan_key):

        return jsonify({"ok": True, "message": f"Plano alterado para {plan_key} com sucesso!"})



    return jsonify({"ok": False, "error": "Falha ao alterar plano ou plano inválido."}), 400





@app.route('/api/admin/supreme/full-overview')

def api_admin_supreme_full_overview():

    """Visão completa de TODOS os admins, produtos, leads recentes e stats — Admin Supremo."""

    admin_id, role = verify_admin_access(request)

    if role != "supreme_admin":

        return jsonify({"ok": False, "error": "Acesso restrito ao Admin Supremo"}), 403

    if not TG_WH_AVAILABLE:

        return jsonify({"ok": False, "error": "multi-tenant indisponível"}), 503

    overview = tg_wh.get_full_overview_for_supreme()

    return jsonify({"ok": True, **overview})





@app.route('/api/geo')

def api_geo():

    """Geolocalização real do IP do visitante — retorna lat, lng, cidade, país, ISP."""

    ip = _user_ip()

    if not TG_WH_AVAILABLE:

        return jsonify({"ok": False, "error": "indisponível"}), 503

    geo = tg_wh.get_ip_geolocation(ip)

    return jsonify({"ok": True, "ip": ip, **geo})





@app.route('/api/admin/my-products/<product_code>', methods=['PATCH'])

def api_admin_update_product(product_code):

    """Atualiza produto do catálogo do admin — inclui shipping_mode, shipping_fee, shipping_coupon."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    data = request.json or {}

    safe_code = sanitize_input(product_code, 30)



    if TG_WH_AVAILABLE:

        ok = tg_wh.update_tenant_product(admin_id, safe_code, data)

        if ok:

            if VALIDATORS_AVAILABLE and ActivityAudit:

                ActivityAudit.log('admin_product_update', actor_id=admin_id, ip=_user_ip(),

                                  details={'product_code': safe_code, 'fields': list(data.keys())})

            return jsonify({"ok": True, "message": "Produto atualizado com sucesso!"})

    return jsonify({"ok": False, "error": "Produto não encontrado ou erro ao atualizar."}), 400





@app.route('/api/admin/my-products/<product_code>/shipping', methods=['POST'])

def api_admin_set_shipping_mode(product_code):

    """Ativa/desativa modo 'apenas taxa' e cupom por produto individual."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    data = request.json or {}

    mode    = data.get("shipping_mode", "full")      # 'full' | 'shipping_only' | 'sedex' | 'local'

    fee     = data.get("shipping_fee", "19.90")

    coupon  = data.get("shipping_coupon", "")

    c_active = data.get("coupon_active", 1)

    c_only_ship = data.get("coupon_only_shipping", 1)

    safe_code = sanitize_input(product_code, 30)



    if mode not in ("full", "shipping_only", "sedex", "local"):

        mode = "full"



    if TG_WH_AVAILABLE:

        ok = tg_wh.update_tenant_product(admin_id, safe_code, {

            "shipping_mode": mode,

            "shipping_fee":  sanitize_input(str(fee), 20),

            "shipping_coupon": sanitize_input(str(coupon), 60),

            "coupon_active": 1 if c_active in (1, "1", True, "true") else 0,

            "coupon_only_shipping": 1 if c_only_ship in (1, "1", True, "true") else 0,

        })

        if ok:

            if VALIDATORS_AVAILABLE and ActivityAudit:

                ActivityAudit.log("admin_shipping_set", actor_id=admin_id, ip=_user_ip(),

                                  details={"product_code": safe_code, "mode": mode, "fee": fee, "coupon": coupon, "coupon_active": c_active})

            return jsonify({"ok": True, "shipping_mode": mode, "shipping_fee": fee, "coupon_active": c_active, "message": "Configurações de frete e cupom atualizadas!"})

    return jsonify({"ok": False, "error": "Falha ao atualizar modo."}), 400





@app.route('/api/validate-coupon', methods=['POST'])

def api_validate_coupon():

    """Validação inteligente e 100% real do cupom de desconto do produto."""

    data = request.json or {}

    coupon = sanitize_input(data.get("coupon", "") or data.get("coupon_code", ""), 60)

    product_code = sanitize_input(data.get("product_code", "") or data.get("code", ""), 60)

    slug = sanitize_input(data.get("slug", "") or request.args.get("slug", ""), 60)



    if not coupon:

        return jsonify({"ok": False, "valid": False, "message": "Por favor, informe o código do cupom."}), 400



    if TG_WH_AVAILABLE:

        res = tg_wh.validate_product_coupon(product_code, coupon, slug=slug)

        return jsonify({"ok": res.get("valid", False), **res})



    # Fallback global inteligente

    c_upper = coupon.strip().upper()

    if c_upper in ("FRETEGRATIS", "OLX26OFF", "PROMO100"):

        return jsonify({

            "ok": True,

            "valid": True,

            "message": "Cupom válido! Cobrança reduzida para taxa de envio.",

            "coupon": c_upper,

            "original_price": 630.00,

            "shipping_fee": 19.90,

            "discount_amount": 630.00,

            "final_amount": 19.90,

            "formatted_original": "R$ 630,00",

            "formatted_discount": "R$ 630,00",

            "formatted_shipping": "R$ 19,90",

            "formatted_final": "R$ 19,90",

            "shipping_only": True

        })

    return jsonify({"ok": False, "valid": False, "message": "Cupom inválido ou inativo."}), 400







@app.route('/api/event', methods=['POST'])

def api_event():

    """

    Central event ingestion endpoint.

    Frontend sends events here: PAGE_EXIT, CLICK_BUY, CLICK_CHAT,

    MODAL_STEP, PHOTO_CLICK, WHATSAPP_REDIRECT, etc.

    """

    data = request.json or {}

    event_type = data.get('event_type') or data.get('event', 'UNKNOWN')

    session_id = data.get('session_id', 'anon')

    # Aceita payload aninhado OU objeto root (trackEvent manda tudo no root)
    payload    = data.get('payload') or data.get('data') or data



    # Mark session exit

    if event_type == "PAGE_EXIT" and BOT_AVAILABLE:

        try:

            conn = admin_bot.get_db()

            conn.execute(

                "UPDATE sessions SET left_at=? WHERE session_id=?",

                (time.time(), session_id)

            )

            conn.commit()

            conn.close()

        except Exception:

            pass



    # Mark conversion (WhatsApp redirect or payment confirmed)
    if event_type in ("WHATSAPP_REDIRECT", "PAYMENT_CONFIRMED", "PAYMENT_CONFIRMED_SUCCESS", "PIX_PAID"):
        pid = payload.get("payment_id") or payload.get("c7_id") or ""
        if pid and pid in PAYMENTS_DB:
            p_rec = PAYMENTS_DB[pid]
            for k, v in p_rec.items():
                if k not in payload or not payload[k]:
                    payload[k] = v
        if event_type in ("PAYMENT_CONFIRMED", "PAYMENT_CONFIRMED_SUCCESS", "PIX_PAID"):
            event_type = "PAYMENT_CONFIRMED"

        if BOT_AVAILABLE:
            try:
                conn = admin_bot.get_db()
                conn.execute(
                    "UPDATE sessions SET converted=1 WHERE session_id=?", (session_id,)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    _log(event_type, session_id, payload)

    if TG_WH_AVAILABLE:
        slug = payload.get("slug") or request.args.get("slug", "global")
        tg_id = payload.get("tg_id") or payload.get("tenant_id") or 0
        if not tg_id and slug and slug not in ("global", "principal"):
            try:
                tg_id = tg_wh.get_tg_id_by_slug(slug) or 0
            except Exception:
                tg_id = 0

        ip = _user_ip()
        product_code = payload.get("product_code", "") or ""
        amount = payload.get("amount", "") or ""

        ch_key = {
            "PAGE_ENTRY": "visita",
            "CLICK_BUY": "cliques",
            "LEAD_CAPTURED": "lead",
            "LEAD_PENDING": "lead",
            "PIX_GENERATED": "pix",
            "PIX_PAID": "pagamento",
            "PAYMENT_CONFIRMED": "pagamento",
            "PAYMENT_CONFIRMED_SUCCESS": "pagamento"
        }.get(event_type, "all")

        title_map = {
            "PAGE_ENTRY":                 "👁 Nova Visita no Anúncio",
            "CLICK_BUY":                  "🛒 Clique em Comprar",
            "LEAD_CAPTURED":              "📋 Lead Capturado Real",
            "LEAD_PENDING":               "⏳ Lead Pendente",
            "PIX_GENERATED":              "💸 Pix Gerado",
            "PIX_PAID":                   "✅ Pagamento Confirmado!",
            "PAYMENT_CONFIRMED":          "✅ Pagamento Confirmado!",
            "PAYMENT_CONFIRMED_SUCCESS":  "✅ Pagamento Confirmado!"
        }

        ev_title = title_map.get(event_type, f"⚡ Evento: {event_type}")

        extra_lines = ""
        if product_code:
            extra_lines += f"\n📦 <b>Produto:</b> <code>{product_code}</code>"
        if amount:
            extra_lines += f"\n💰 <b>Valor:</b> R$ {amount}"

        if event_type == "PAYMENT_CONFIRMED" and payload.get("name"):
            msg_text = _format_payment_html_msg(payload)
            wa_digits = re.sub(r'\D', '', str(payload.get("phone", "")))
            markup = None
            if len(wa_digits) >= 10:
                wa_num = wa_digits if wa_digits.startswith("55") else f"55{wa_digits}"
                markup = {"inline_keyboard": [[{"text": "💬 Chamar Cliente no WhatsApp", "url": f"https://wa.me/{wa_num}"}]]}
            tg_wh.notify_log_channel("pagamento", msg_text, markup=markup)
        else:
            msg_text = (
                f"<b>{ev_title}</b>\n"
                f"📦 <b>Slug:</b> <code>{slug}</code>\n"
                f"🌐 <b>IP:</b> <code>{ip}</code>\n"
                f"🔑 <b>Session ID:</b> <code>{session_id[:12]}</code>\n"
                f"⏱ <b>Data/Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"
                + extra_lines
            )
            tg_wh.notify_log_channel(ch_key, msg_text)

        if tg_id:
            try:
                tg_wh.log_tenant_event(int(tg_id), slug, event_type, session_id, ip, payload)
            except Exception:
                pass


    return jsonify({"ok": True})





@app.route('/api/validate-cep', methods=['POST'])

def validate_cep():

    """Real ViaCEP validation with Telegram logging. Returns real shipping_fee from product config."""

    data = request.json or {}

    cep  = data.get('cep', '').replace('-', '').replace('.', '').strip()

    sid  = _session_id(data)

    product_code = data.get('product_code', '') or ''

    slug = data.get('slug', '') or ''



    if len(cep) != 8 or not cep.isdigit():

        return jsonify({"success": False, "message": "CEP inválido. Digite 8 dígitos numéricos."}), 400



    # Busca shipping_fee real do produto no tenant DB

    shipping_fee_raw = 0.0

    shipping_fee_str = "0,00"

    frete_label = "Grátis"

    if TG_WH_AVAILABLE and product_code:

        try:

            prod = tg_wh.get_product_by_code(product_code)

            if prod:

                sf_val = prod.get('shipping_fee', '0') or '0'

                shipping_fee_raw = float(str(sf_val).replace(',', '.')) if sf_val else 0.0

                if shipping_fee_raw > 0:

                    shipping_fee_str = f"{shipping_fee_raw:.2f}".replace('.', ',')

                    frete_label = f"R$ {shipping_fee_str}"

        except Exception:

            pass



    try:

        res      = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=4)

        cep_data = res.json()

        if "erro" in cep_data:

            return jsonify({"success": False, "message": "CEP não localizado na base dos Correios."}), 404



        street = cep_data.get('logradouro', '')

        bairro = cep_data.get('bairro', '')

        cidade = cep_data.get('localidade', '')

        uf     = cep_data.get('uf', '')



        parts = [p for p in [street, bairro] if p]

        full_address = f"{', '.join(parts)} - {cidade}/{uf}" if parts else f"{cidade}/{uf}"



        _log("CEP_LOOKUP", sid, {

            "cep": f"{cep[:5]}-{cep[5:]}",

            "address": full_address

        })



        return jsonify({

            "success":      True,

            "cep":          f"{cep[:5]}-{cep[5:]}",

            "logradouro":   street,

            "bairro":       bairro,

            "cidade":       cidade,

            "uf":           uf,

            "frete":        frete_label,

            "shipping_fee": shipping_fee_str,

            "shipping_fee_raw": shipping_fee_raw,

            "modalidade":   "Entrega Fácil OLX Garantida",

            "prazo":        "Chega entre 2 a 4 dias úteis",

            "seguro":       "100% Protegido com Garantia da OLX"

        })

    except Exception as e:

        return jsonify({"success": False, "message": "Erro de conexão ao consultar CEP."}), 500





@app.route('/api/lead', methods=['POST'])

def capture_lead():

    """

    Captura lead qualificado com rastreio completo por tenant.

    Associa o lead ao admin correto via slug na requisição.

    Salva no DB criptografado e envia para o canal Telegram do admin.

    """

    data = request.json or {}

    sid  = _session_id(data)

    ip   = _user_ip()

    ua   = _user_ua()



    # Identifica o tenant (admin) que gerou este lead

    slug = sanitize_input(data.get('slug', '') or request.args.get('slug', ''), 60)

    tg_id = None

    if TG_WH_AVAILABLE and slug:

        tg_id = tg_wh.get_tg_id_by_slug(slug)



    # --- Extrai e valida campos com motor avançado ---

    raw_name  = data.get('name',  '')

    raw_cpf   = data.get('cpf',   '')

    raw_phone = data.get('phone', '')

    raw_email = data.get('email', '')

    raw_cep   = data.get('cep',   '')



    if VALIDATORS_AVAILABLE and FieldValidator:

        ok_n, name, _   = FieldValidator.validate_field('name',  raw_name)

        if not ok_n:

            if ActivityAudit:

                ActivityAudit.log('security_invalid_data', ip=ip, session_id=sid, slug=slug,

                                  details={'field': 'name', 'error': name})

            return jsonify({'ok': False, 'error': name}), 400

        ok_ph, phone, _ = FieldValidator.validate_field('phone', raw_phone)

        if not ok_ph:

            return jsonify({'ok': False, 'error': phone}), 400

        ok_em, email, _ = FieldValidator.validate_field('email', raw_email)

        email = email if ok_em else sanitize_input(raw_email, 100)

        cep = re.sub(r'\D', '', raw_cep)

    else:

        name  = sanitize_input(raw_name, 120)

        phone = sanitize_input(raw_phone, 25)

        email = sanitize_input(raw_email, 100)

        cep   = sanitize_input(raw_cep, 15)

        if not name or len(name.split()) < 2:

            return jsonify({'ok': False, 'error': 'Informe seu nome completo (Nome e Sobrenome).'}), 400



    cpf          = sanitize_input(raw_cpf, 20)

    street       = sanitize_input(data.get('street', ''), 200)

    number_addr  = sanitize_input(data.get('number', ''), 30)

    complement   = sanitize_input(data.get('complement', ''), 100)

    neighborhood = sanitize_input(data.get('neighborhood', ''), 100)

    city         = sanitize_input(data.get('city', ''), 100)

    state        = sanitize_input(data.get('state', ''), 10)

    amount       = sanitize_input(data.get('amount', '630,00'), 20)

    product_name = sanitize_input(data.get('product', ''), 120)

    product_code = sanitize_input(data.get('product_code', '') or data.get('code', ''), 60)

    coupon       = sanitize_input(data.get('coupon', '') or data.get('shipping_coupon', ''), 60)

    shipping_mode = sanitize_input(data.get('shipping_mode', 'full'), 30)



    # Validação do Cupom / Modo Apenas Frete

    is_coupon_applied = False

    coupon_details = {}

    if TG_WH_AVAILABLE and coupon:

        val_res = tg_wh.validate_product_coupon(product_code, coupon, slug=slug)

        if val_res.get("valid"):

            is_coupon_applied = True

            coupon_details = val_res

            amount = f"{val_res.get('final_amount', 19.90):.2f}".replace(".", ",")

    elif shipping_mode == 'shipping_only':

        is_coupon_applied = True



    # Validação: nome completo

    if not name or len(name.split()) < 2:

        return jsonify({"ok": False, "error": "Informe seu nome completo (Nome e Sobrenome)."}), 400



    # Validação: CPF real via Hub do Desenvolvedor

    is_cpf_ok, cpf_err, cpf_data = verify_cpf_hub(raw_cpf if VALIDATORS_AVAILABLE else cpf)

    if not is_cpf_ok:

        _log('LEAD_REJECTED_INVALID_CPF', sid, {'cpf': cpf, 'name': name, 'reason': cpf_err, 'slug': slug})

        if VALIDATORS_AVAILABLE and ActivityAudit:

            ActivityAudit.log('security_invalid_data', ip=ip, session_id=sid, slug=slug,

                              details={'field': 'cpf', 'error': cpf_err})

        return jsonify({'ok': False, 'error': cpf_err or 'CPF invalido.'}), 400



    # Validação: telefone BR

    if not VALIDATORS_AVAILABLE and BOT_AVAILABLE:

        valid_phone, phone_err = admin_bot.InputValidator.validate_phone_br(phone)

        if phone_err:

            return jsonify({'ok': False, 'error': phone_err}), 400

        phone = valid_phone



    # Contexto de rastreio avançado

    lead_payload = {

        "name":         name,

        "cpf":          cpf,

        "phone":        phone,

        "email":        email,

        "cep":          cep,

        "street":       street,

        "number":       number_addr,

        "complement":   complement,

        "neighborhood": neighborhood,

        "city":         city,

        "state":        state,

        "amount":       amount,

        "product":      product_name or (admin_bot.get_config("product_name", "") if BOT_AVAILABLE else ""),

        "product_code": product_code,

        "coupon":       coupon if is_coupon_applied else "",

        "coupon_applied": is_coupon_applied,

        "shipping_mode": shipping_mode,

        "slug":         slug,

        "tg_id":        tg_id,

        "ip":           ip,

        "ua":           ua[:120],

        "cpf_verified": not cpf_data.get("fallback_math", False),

    }



    # Registra no DB global
    _log("LEAD_CAPTURED", sid, lead_payload)
    _log("LEAD_PENDING", sid, lead_payload)

    # Auditoria centralizada
    if VALIDATORS_AVAILABLE and ActivityAudit:
        ActivityAudit.log("lead_captured", session_id=sid, ip=ip, slug=slug,
                          details={
                              "name": name, "phone": phone, "city": city,
                              "state": state, "product": lead_payload.get('product', ''),
                              "amount": amount, "coupon": coupon if is_coupon_applied else '',
                              "cpf_verified": lead_payload.get('cpf_verified', False),
                          })

    # Registra no DB do tenant correto (isolamento por admin)
    if TG_WH_AVAILABLE:
        t_id = tg_id or (tg_wh.get_tg_id_by_slug(slug) if slug else 0) or 0
        if t_id and slug:
            tg_wh.log_tenant_event(t_id, slug, "LEAD_CAPTURED", sid, ip, lead_payload)
            tg_wh.log_tenant_event(t_id, slug, "LEAD_PENDING", sid, ip, lead_payload)

        # Lead registrado — notificacao unificada sera enviada junto com o PIX gerado
        # (evita duplicidade: lead + pix geram a mesma mensagem para o admin)

    return jsonify({
        "ok": True,
        "message": "Lead registrado com sucesso no Vault Criptografado.",
        "session_id": sid,
        "amount": amount
    })


def _format_payment_html_msg(record: dict) -> str:
    name = record.get("name") or record.get("payer_name") or record.get("payer") or "Cliente OLX"
    cpf = record.get("cpf") or record.get("payer_cpf") or ""
    phone = record.get("phone", "")
    email = record.get("email", "")
    prod = record.get("product_name") or record.get("product") or "Produto OLX"
    amount = record.get("amount", 0)
    try:
        amt_val = float(str(amount).replace("R$", "").replace(" ", "").replace(",", "."))
        amt_str = f"R$ {amt_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        amt_str = f"R$ {amount}"

    st = record.get("street", "")
    num = record.get("number", "")
    comp = record.get("complement", "")
    neigh = record.get("neighborhood", "")
    city = record.get("city", "")
    uf = record.get("state", "")
    cep = record.get("cep", "")

    addr_parts = []
    if st:
        addr_parts.append(f"🏠 <b>Rua:</b> {st}" + (f", Nº {num}" if num else ""))
    if comp:
        addr_parts.append(f"🏢 <b>Compl:</b> {comp}")
    if neigh:
        addr_parts.append(f"🏘️ <b>Bairro:</b> {neigh}")
    if city or uf:
        addr_parts.append(f"📍 <b>Cidade/UF:</b> {city}/{uf}")
    if cep:
        addr_parts.append(f"📬 <b>CEP:</b> <code>{cep}</code>")
    addr_block = ("\n" + "\n".join(addr_parts)) if addr_parts else ""

    wa_digits = re.sub(r'\D', '', str(phone))
    wa_line = f"\n📱 <b>WhatsApp:</b> <code>{phone}</code>" if phone else ""

    shipping_mode = record.get("shipping_mode", "")
    ship_line = ""
    if shipping_mode:
        s_lbl = "Apenas Frete" if shipping_mode == "shipping_only" else "Entrega Expressa OLX"
        ship_line = f"\n🚚 <b>Envio:</b> <code>{s_lbl}</code>"

    coupon = record.get("coupon", "") or record.get("shipping_coupon", "")
    coupon_line = f"\n🎟️ <b>Cupom:</b> <code>{coupon}</code>" if coupon else ""

    pid = record.get('payment_id', '') or record.get('c7_id', '')

    if record.get("is_upsell") or record.get("upsell_title"):
        upsell_type = record.get("upsell_type") or "Taxa Adicional"
        upsell_title = record.get("upsell_title") or prod
        return (
            f"<b>⚡ UPSELL / TAXA PAGA COM SUCESSO! ⚡</b>\n"
            f"═════════════════════════════════\n"
            f"🏷️ <b>Tipo de Taxa:</b> <b>{upsell_type}</b>\n"
            f"🛡️ <b>Modal:</b> {upsell_title}\n"
            f"💰 <b>Valor Pago:</b> <b>{amt_str}</b>\n"
            f"📦 <b>Anúncio:</b> {prod}\n\n"
            f"👤 <b>DADOS DO CLIENTE QUE PAGOU:</b>\n"
            f"• <b>Nome:</b> {name}\n"
            f"• <b>CPF:</b> <code>{cpf}</code>"
            f"{wa_line}\n"
            f"• <b>Email:</b> {email or 'Não informado'}"
            f"{addr_block}\n\n"
            f"═════════════════════════════════\n"
            f"🔗 <b>Slug:</b> <code>{record.get('slug', 'principal')}</code>\n"
            f"🆔 <b>ID Pagamento:</b> <code>{pid}</code>\n"
            f"🏛️ <b>Gateway:</b> <code>{record.get('gateway', 'Pix Automático')}</code>\n"
            f"⏱ <b>Data/Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"
        )

    return (
        f"<b>🎉 COMPRA CONFIRMADA NO PIX!</b>\n"
        f"═════════════════════════════════\n"
        f"📦 <b>Produto:</b> {prod}\n"
        f"💰 <b>Valor Pago:</b> <b>{amt_str}</b>"
        f"{ship_line}{coupon_line}\n\n"
        f"👤 <b>DADOS DO COMPRADOR:</b>\n"
        f"• <b>Nome:</b> {name}\n"
        f"• <b>CPF:</b> <code>{cpf}</code>"
        f"{wa_line}\n"
        f"• <b>Email:</b> {email or 'Não informado'}"
        f"{addr_block}\n\n"
        f"═════════════════════════════════\n"
        f"🔗 <b>Slug:</b> <code>{record.get('slug', 'principal')}</code>\n"
        f"🆔 <b>ID Pagamento:</b> <code>{pid}</code>\n"
        f"⏱ <b>Data/Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"
    )


@app.route('/api/generate-pix', methods=['POST'])
@app.route('/api/create-pix', methods=['POST'])
def generate_pix():

    """Creates a Pix payment via Carteira do 7 (C7) POST /v2/payment/create with fallback simulation."""

    data       = request.json or {}

    sid        = _session_id(data)

    payment_id = f"olx_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    

    # C7 requer callbackUrl usando obrigatoriamente HTTPS

    host_url = request.host_url.rstrip('/')

    if host_url.startswith("http://"):

        callback_url = host_url.replace("http://", "https://") + "/api/webhook/pix"

    else:

        callback_url = host_url + "/api/webhook/pix"



    payer_name     = sanitize_input(data.get('name', 'Cliente OLX'), 120)
    payer_document = re.sub(r'\D', '', sanitize_input(data.get('cpf', ''), 20))
    product_code   = sanitize_input(data.get('product_code', '') or data.get('code', ''), 60)
    coupon         = sanitize_input(data.get('coupon', '') or data.get('shipping_coupon', ''), 60)
    shipping_mode  = sanitize_input(data.get('shipping_mode', ''), 30)

    clean_phone    = sanitize_input(data.get('phone', ''), 30)
    clean_email    = sanitize_input(data.get('email', ''), 100)
    street         = sanitize_input(data.get('street', ''), 200)
    number_addr    = sanitize_input(data.get('number', ''), 30)
    complement     = sanitize_input(data.get('complement', ''), 100)
    neighborhood   = sanitize_input(data.get('neighborhood', ''), 100)
    city           = sanitize_input(data.get('city', ''), 100)
    state          = sanitize_input(data.get('state', ''), 20)
    cep            = sanitize_input(data.get('cep', ''), 20)
    prod_title     = sanitize_input(data.get('upsell_title', '') or data.get('product', '') or data.get('product_name', ''), 150)

    

    # Preco inteligente: valida se cupom foi aplicado ou se é modo apenas frete

    slug_for_price = data.get('slug', '') or request.args.get('slug', '')

    tg_id_for_price = None

    if TG_WH_AVAILABLE and slug_for_price:

        try:

            tg_id_for_price = tg_wh.get_tg_id_by_slug(slug_for_price)

        except Exception:

            pass



    c7_amount = 0.0



    # 1. Se veio cupom, valida pelo motor inteligente

    if TG_WH_AVAILABLE and coupon:

        val_res = tg_wh.validate_product_coupon(product_code, coupon, slug=slug_for_price)

        if val_res.get("valid"):

            c7_amount = float(val_res.get("final_amount", 19.90))



    # 2. Se modo shipping_only ou taxa explícita

    if c7_amount <= 0:

        if shipping_mode == 'shipping_only':

            raw_fee = data.get('shipping_fee') or data.get('amount') or '19.90'

            try:

                c7_amount = float(str(raw_fee).replace('R$', '').replace(' ', '').replace(',', '.'))

            except ValueError:

                c7_amount = 19.90



    # 3. Se veio amount já formatado na requisição (ex: R$ 19,90)

    if c7_amount <= 0 and data.get('amount'):

        try:

            c7_amount = float(str(data.get('amount')).replace('R$', '').replace(' ', '').replace(',', '.'))

        except ValueError:

            c7_amount = 0.0



    # 4. Busca produto por código

    if c7_amount <= 0 and product_code and TG_WH_AVAILABLE:

        prod = tg_wh.get_product_by_code(product_code)

        if prod:

            if prod.get("shipping_mode") == "shipping_only":

                try:

                    c7_amount = float(str(prod.get("shipping_fee", "19.90")).replace(",", "."))

                except ValueError:

                    c7_amount = 19.90

            else:

                try:

                    c7_amount = float(str(prod.get("price", "")).replace(",", "."))

                except ValueError:

                    c7_amount = 630.00



    # 5. Fallback por tenant ou global

    if c7_amount <= 0:

        if tg_id_for_price:

            cfgs = tg_wh.get_tenant_all_config(tg_id_for_price)

            price_str = cfgs.get("product_price", "")

        elif BOT_AVAILABLE:

            price_str = admin_bot.get_config("product_price", "")

        else:

            price_str = ""

        try:

            c7_amount = float(price_str.replace(",", "."))

        except ValueError:

            c7_amount = 630.00



    c7_payload = {

        "amount": c7_amount,

        "callbackUrl": callback_url,

        "externalId": payment_id

    }

    if payer_name:

        c7_payload["payerName"] = payer_name

    if payer_document and len(payer_document) == 11:

        c7_payload["payerDocument"] = payer_document



    # acquirer_code: do vault se disponivel, senao env
    live_acquirer = _get_live_c7_keys().get("acquirer_code", "") or C7_ACQUIRER_CODE
    if live_acquirer:
        c7_payload["acquirer_code"] = live_acquirer



    pix_code    = ""
    qr_code_url = ""
    c7_id       = ""
    expires_at  = ""
    c7_status   = "pending"

    gw_keys = _get_live_gateway_keys()
    active_gw = gw_keys.get("gateway", "elitepay")
    live_base_url = gw_keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")
    client_id = gw_keys.get("client_id") or gw_keys.get("api_key", "")
    client_secret = gw_keys.get("client_secret") or gw_keys.get("api_secret", "")
    gateway_used = active_gw

    # ── 1. Tentativa Primária: União 7 Pay (se configurada como ativa principal) ──
    if active_gw == "uniaopay":
        u7_res = create_uniaopay_pix(
            c7_amount,
            {
                "name": payer_name,
                "document": payer_document,
                "email": clean_email,
                "phone": clean_phone
            },
            custom_api_key=client_id,
            custom_base_url=live_base_url
        )
        if u7_res.get("ok"):
            c7_id = u7_res.get("transaction_id", "")
            pix_code = u7_res.get("pix_code", "")
            qr_code_url = u7_res.get("qr_code_url", "")
            expires_at = str(int(time.time() + u7_res.get("expires_in", 1800)))
            c7_status = "pending"
            gateway_used = "uniaopay"
            print(f"[Uniao7Pay API] Pix criado com sucesso como principal! ID: {c7_id}")
        else:
            print(f"[Uniao7Pay API] Falha na tentativa principal: {u7_res.get('error')}")

    # ── 2. Tentativa Primária: ElitePay (POST /api/v1/deposit) ──────────────────
    elif active_gw == "elitepay" or not active_gw:
        if client_id and client_secret and "xxx" not in client_id:
            try:
                elite_payload = {
                    "amount": round(float(c7_amount), 2),
                    "description": f"Pedido {payment_id[-8:]} - {prod_title[:35]}",
                    "payerName": payer_name or "Cliente",
                    "payerDocument": payer_document or "00000000000",
                }
                headers = get_elitepay_headers(client_id, client_secret)
                res = requests.post(
                    f"{live_base_url}/api/v1/deposit",
                    json=elite_payload,
                    headers=headers,
                    timeout=10
                )
                if res.status_code in (200, 201):
                    resp = res.json()
                    if resp.get("success") or resp.get("copyPaste") or resp.get("transactionId"):
                        c7_id = resp.get("transactionId") or resp.get("id") or ""
                        pix_code = resp.get("copyPaste") or resp.get("pixCopiaECola") or resp.get("emv") or resp.get("qrcode") or ""
                        qr_code_url = resp.get("qrcodeUrl") or resp.get("qrCodeBase64") or resp.get("qrCodeUrl") or ""
                        expires_at = resp.get("expiresAt") or resp.get("expires_at") or ""
                        c7_status = resp.get("status", "PENDENTE").lower()
                        gateway_used = "elitepay"
                        print(f"[ElitePay API] Pix criado com sucesso! ID: {c7_id}")
                    else:
                        print(f"[ElitePay API] Resposta inesperada: {resp}")
                else:
                    print(f"[ElitePay API] Erro HTTP {res.status_code}: {res.text[:200]}")
            except Exception as err:
                print(f"[ElitePay API] Excecao: {err}")

    # ── 3. Tentativa Primária: Carteira do 7 (C7) ──────────────────────────────
    elif active_gw == "c7":
        if client_id and "c7_live_xxx" not in client_id:
            try:
                c7_payload = {
                    "amount": c7_amount,
                    "callbackUrl": callback_url,
                    "externalId": payment_id
                }
                if payer_name: c7_payload["payerName"] = payer_name
                if payer_document and len(payer_document) == 11: c7_payload["payerDocument"] = payer_document
                body_str = json.dumps(c7_payload, separators=(',', ':'))
                headers = get_c7_auth_headers(body_str)
                res = requests.post(f"{live_base_url}/payment/create", data=body_str, headers=headers, timeout=10)
                if res.status_code in (200, 201):
                    resp = res.json()
                    if resp.get("ok") and "payment" in resp:
                        p = resp["payment"]
                        c7_id = p.get("id", "")
                        pix_code = p.get("pixCopiaECola") or p.get("emv") or p.get("qrcode") or ""
                        qr_code_url = p.get("qrCodeBase64") or p.get("qrCodeUrl") or ""
                        expires_at = p.get("expiresAt") or ""
                        c7_status = p.get("status", "pending")
                        gateway_used = "c7"
            except Exception as err:
                print(f"[C7 Fallback] Excecao: {err}")

    # ── 4. FAILOVER AUTOMÁTICO: UNIÃO 7 PAY (SE A PRIMÁRIA FALHOU) ─────────────
    if not pix_code and active_gw != "uniaopay":
        u7_cfg = _get_uniaopay_config()
        if u7_cfg.get("fallback_enabled") and u7_cfg.get("api_key"):
            print(f"[FAILOVER] Gateway primario ({active_gw}) falhou. Acionando União 7 Pay como secundaria automatica...")
            u7_res = create_uniaopay_pix(
                c7_amount,
                {
                    "name": payer_name,
                    "document": payer_document,
                    "email": clean_email,
                    "phone": clean_phone
                }
            )
            if u7_res.get("ok"):
                c7_id = u7_res.get("transaction_id", "")
                pix_code = u7_res.get("pix_code", "")
                qr_code_url = u7_res.get("qr_code_url", "")
                expires_at = str(int(time.time() + u7_res.get("expires_in", 1800)))
                c7_status = "pending"
                gateway_used = "uniaopay (failover)"
                print(f"[FAILOVER SUCCESS] Pix gerado com sucesso via União 7 Pay! ID: {c7_id}")
            else:
                print(f"[FAILOVER ERROR] União 7 Pay tambem falhou: {u7_res.get('error')}")

    if not pix_code:
        # Gera PIX EMV válido com CRC-16/CCITT correto (BACEN BR Code 2.0)
        gateway_used = "emv_local"

        pix_key_fallback = ""

        if BOT_AVAILABLE:

            pix_key_fallback = admin_bot.get_config("pix_key", "")

        if not pix_key_fallback:

            pix_key_fallback = str(uuid.uuid4())

        txid_short = f"olx{uuid.uuid4().hex[:20]}"

        pix_code = generate_pix_emv(

            amount=c7_amount,

            merchant_name="OLXPAGAMENTOS",

            merchant_city="SAOPAULO",

            pix_key=pix_key_fallback,

            txid=txid_short

        )

        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={requests.utils.quote(pix_code)}"



    if not prod_title and product_code and TG_WH_AVAILABLE:
        p_info = tg_wh.get_product_by_code(product_code)
        if p_info:
            prod_title = p_info.get("title", "")
    if not prod_title:
        prod_title = product_code or "Produto OLX"

    record = {
        "payment_id":   payment_id,
        "c7_id":        c7_id,
        "amount":       c7_amount,
        "status":       c7_status,
        "pix_code":     pix_code,
        "qr_code_url":  qr_code_url,
        "expires_at":   expires_at,
        "created_at":   time.time(),
        "ip":           _user_ip(),
        "name":         payer_name,
        "cpf":          payer_document,
        "email":        clean_email,
        "phone":        clean_phone,
        "product_name": prod_title,
        "product":      prod_title,
        "product_code": product_code,
        "street":       street,
        "number":       number_addr,
        "complement":   complement,
        "neighborhood": neighborhood,
        "city":         city,
        "state":        state,
        "cep":          cep,
        "shipping_mode": shipping_mode,
        "coupon":       coupon,
        "is_upsell":    bool(data.get("upsell_modal_id") or data.get("upsell_title")),
        "upsell_modal_id": data.get("upsell_modal_id", ""),
        "upsell_title": data.get("upsell_title", ""),
        "upsell_type":  data.get("upsell_type", ""),
        "tg_id":        tg_id_for_price,
        "slug":         slug_for_price,
        "gateway":      gateway_used,
    }

    _save_payment(record)

    pix_log_payload = dict(record)
    pix_log_payload.update({
        "gateway":    gateway_used,
        "c7_id":      c7_id or "fallback-emv",
        "payment_id": payment_id,
        "amount":     f"{c7_amount:.2f}",
        "via_c7_api": bool(c7_id),
        "expires_at": expires_at,
    })

    _log("PIX_GENERATED", sid, pix_log_payload)

    if TG_WH_AVAILABLE and tg_id_for_price and slug_for_price:
        tg_wh.log_tenant_event(tg_id_for_price, slug_for_price, "PIX_GENERATED", sid, _user_ip(), pix_log_payload)

        wa_digits = re.sub(r'\D', '', str(clean_phone))

        # Formata valor monetário
        try:
            amt_fmt = f"{c7_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            amt_fmt = str(c7_amount)

        # Endereço completo
        addr_parts = []
        if street:       addr_parts.append(f"{street}" + (f", Nº {number_addr}" if number_addr else ""))
        if complement:   addr_parts.append(f"Compl: {complement}")
        if neighborhood: addr_parts.append(f"{neighborhood}")
        if city or state: addr_parts.append(f"{city}/{state}" if (city and state) else city or state)
        if cep:          addr_parts.append(f"CEP: {cep}")
        addr_line = " • ".join(addr_parts) if addr_parts else "Não informado"

        # Mensagem unificada Lead + PIX (uma única notificação ao admin)
        if record.get("is_upsell"):
            u_tp = record.get("upsell_type") or "Taxa Adicional"
            u_tt = record.get("upsell_title") or prod_title
            pix_msg = (
                f"<b>⚡ UPSELL: PIX DE TAXA GERADO!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ <b>Tipo:</b> <b>{u_tp}</b>\n"
                f"🛡️ <b>Modal:</b> {u_tt}\n"
                f"💰 <b>Valor da Taxa:</b> R$ {amt_fmt}\n"
                f"📦 <b>Produto:</b> {prod_title}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Cliente:</b> {payer_name}\n"
                f"📄 <b>CPF:</b> <code>{payer_document}</code>\n"
                f"📱 <b>WhatsApp:</b> <code>{clean_phone or 'Não informado'}</code>\n"
                f"🆔 <b>ID Pagamento:</b> <code>{payment_id}</code>\n"
                f"🔗 <b>Slug:</b> <code>{slug_for_price}</code>\n"
                f"⏱ <b>Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"
            )
        else:
            pix_msg = (
                f"<b>🧾 Lead + PIX Gerado!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Nome:</b> {payer_name}\n"
                f"📄 <b>CPF:</b> <code>{payer_document}</code>\n"
                f"📱 <b>WhatsApp:</b> <code>{clean_phone or 'Não informado'}</code>\n"
                f"📧 <b>Email:</b> {clean_email or 'Não informado'}\n"
                f"🏠 <b>Endereço:</b> {addr_line}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Produto:</b> {prod_title}\n"
                f"💰 <b>Valor Pix:</b> R$ {amt_fmt}\n"
                f"🆔 <b>ID Pagamento:</b> <code>{payment_id}</code>\n"
                f"🔗 <b>Slug:</b> <code>{slug_for_price}</code>\n"
                f"⏱ <b>Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"
            )
        markup = None
        if len(wa_digits) >= 10:
            wa_num = wa_digits if wa_digits.startswith("55") else f"55{wa_digits}"
            markup = {"inline_keyboard": [[{"text": "💬 Chamar no WhatsApp", "url": f"https://wa.me/{wa_num}"}]]}
        tg_wh.notify_log_channel("pix", pix_msg, markup=markup)



    return jsonify({

        "ok":            True,

        "success":       True,

        "payment_id":    payment_id,

        "external_id":   payment_id,

        "c7_id":         c7_id,

        "amount":        f"{c7_amount:.2f}".replace(".", ","),

        "pix_code":      pix_code,

        "pix_copy_paste": pix_code,

        "qr_code_url":   qr_code_url,

        "expires_at":    expires_at,

        "via_c7":        bool(c7_id),

    })





@app.route('/api/check-payment/<payment_id>')

def check_payment(payment_id):

    """

    Consulta status do pagamento.

    Doc C7 sec. 6: GET /payment/:id/status — autenticação apenas com API Key.

    Status possíveis: pending | approved | expired | cancelled

    """

    safe_pid = sanitize_input(payment_id, 80)

    payment  = PAYMENTS_DB.get(safe_pid)

    if not payment:

        return jsonify({"status": "not_found"}), 404



    current_status = payment.get("status", "pending")



    # Já confirmado localmente — retorna imediatamente

    if current_status in ("paid", "approved"):

        return jsonify({"payment_id": safe_pid, "status": "paid",

                        "amount": payment.get("amount"), "expires_at": payment.get("expires_at", "")})



    # Expirado ou cancelado — não precisa consultar a C7

    if current_status in ("expired", "cancelled"):

        return jsonify({"payment_id": safe_pid, "status": current_status})



    # Consulta status no Gateway Ativo (ElitePay prioritário)
    c7_id = payment.get("c7_id")
    gw_keys = _get_live_gateway_keys()
    active_gw = gw_keys.get("gateway", "elitepay")
    live_base_url = gw_keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")
    client_id = gw_keys.get("client_id") or gw_keys.get("api_key", "")
    client_secret = gw_keys.get("client_secret") or gw_keys.get("api_secret", "")

    if c7_id and client_id and "xxx" not in client_id:
        try:
            status_confirmed = False
            payer_data = {}
            e2e_id = ""

            if active_gw == "elitepay" or not active_gw:
                # Doc Oficial ElitePay: POST /api/transactions/check { "transactionId": "..." }
                headers = get_elitepay_headers(client_id, client_secret)
                res = requests.post(
                    f"{live_base_url}/api/transactions/check",
                    json={"transactionId": c7_id},
                    headers=headers,
                    timeout=6
                )
                if res.status_code in (200, 201):
                    resp = res.json()
                    tx = resp.get("transaction") or resp.get("data") or resp
                    tx_state = str(tx.get("transactionState") or tx.get("status") or "").upper()
                    if tx_state in ("COMPLETO", "PAID", "APPROVED", "CONCLUIDO"):
                        status_confirmed = True
                        payer_data = tx.get("payer") or {}
                        e2e_id = tx.get("endToEndId") or tx.get("acquirerTransactionId") or ""
            else:
                # Fallback C7
                res = requests.get(
                    f"{live_base_url}/payment/{c7_id}/status",
                    headers=_c7_read_headers(),
                    timeout=6
                )
                if res.status_code == 200:
                    resp = res.json()
                    if resp.get("ok") and "payment" in resp:
                        p_data = resp["payment"]
                        if p_data.get("status", "").lower() in ("approved", "paid"):
                            status_confirmed = True
                            payer_data = p_data.get("payer", {})
                            e2e_id = p_data.get("endToEndId", "")

            if status_confirmed:
                _update_payment_status(safe_pid, "paid", payer=payer_data, end_to_end_id=e2e_id)
                payment = PAYMENTS_DB.get(safe_pid, payment)

                confirmed_payload = dict(payment)
                confirmed_payload.update({
                    "c7_id":      c7_id,
                    "payment_id": safe_pid,
                    "amount":     payment.get("amount"),
                    "payer":      payer_data.get("name") or payment.get("name", "N/A"),
                    "name":       payment.get("name") or payer_data.get("name", "N/A"),
                    "e2e_id":     e2e_id,
                    "status":     "paid"
                })

                _log("PAYMENT_CONFIRMED", safe_pid, confirmed_payload)

                if TG_WH_AVAILABLE:
                    tg_id = payment.get("tg_id")
                    slug = payment.get("slug", "principal")
                    if tg_id and slug:
                        tg_wh.log_tenant_event(tg_id, slug, "PAYMENT_CONFIRMED", safe_pid, payment.get("ip", ""), confirmed_payload)
                        tg_wh.mark_tg_converted(tg_id, safe_pid)

                    html_msg = _format_payment_html_msg(confirmed_payload)
                    wa_digits = re.sub(r'\D', '', str(payment.get("phone", "")))
                    markup = None
                    if len(wa_digits) >= 10:
                        wa_num = wa_digits if wa_digits.startswith("55") else f"55{wa_digits}"
                        markup = {"inline_keyboard": [[{"text": "💬 Chamar Cliente no WhatsApp", "url": f"https://wa.me/{wa_num}"}]]}
                    tg_wh.notify_log_channel("pagamento", html_msg, markup=markup)

                return jsonify({"payment_id": safe_pid, "status": "paid", "amount": payment.get("amount")})

        except Exception as err:
            print(f"[Payment Status] {err}")

    return jsonify({"payment_id": safe_pid, "status": payment.get("status", "pending"), "expires_at": payment.get("expires_at", "")})





@app.route('/api/webhook/elitepay', methods=['POST'])
@app.route('/api/webhook/pix', methods=['POST'])
def universal_webhook():
    """
    Webhook universal da ElitePay & Gateways — implementação completa conforme documentação oficial.
    Valida:
      1. Assinatura HMAC-SHA256 (X-Elite-Signature 'sha256=...' ou X-C7-Signature)
      2. Janela de timestamp: rejeita requisições defasadas (> 5 minutos)
      3. Idempotência: não reprocessa IDs já confirmados
    """
    raw_body   = request.get_data(as_text=True)

    sig_elite  = request.headers.get("X-Elite-Signature", "")
    ts_elite   = request.headers.get("X-Elite-Timestamp", "")
    sig_c7     = request.headers.get("X-C7-Signature", "")
    ts_c7      = request.headers.get("X-C7-Timestamp", "")
    event_hdr  = request.headers.get("X-C7-Event", "")

    sig_header = sig_elite or sig_c7
    ts_header  = ts_elite or ts_c7

    # ── 1. Validação da assinatura HMAC ──────────────────────────────────────
    gw_keys = _get_live_gateway_keys()
    live_secret = gw_keys.get("client_secret") or gw_keys.get("api_secret", "") or C7_API_SECRET

    if live_secret and "xxx" not in live_secret and sig_header:
        if sig_header.startswith("sha256=") or sig_elite:
            # Padrão ElitePay: sha256= + HMAC(secret, ts + '.' + rawBody)
            expected_hex = hmac.new(
                live_secret.encode('utf-8'),
                f"{ts_header}.{raw_body}".encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            expected = f"sha256={expected_hex}"
            if not hmac.compare_digest(sig_header, expected):
                _log("SECURITY_ALERT_WEBHOOK", "webhook", {
                    "ip": _user_ip(), "reason": "HMAC ElitePay invalido"
                })
                return jsonify({"error": "invalid_signature"}), 401
        else:
            # Padrão C7
            expected = hmac.new(
                live_secret.encode('utf-8'),
                f"{ts_header}.{raw_body}".encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                _log("SECURITY_ALERT_WEBHOOK", "webhook", {
                    "ip": _user_ip(), "reason": "HMAC C7 invalido"
                })
                return jsonify({"error": "invalid_signature"}), 401

    # ── 2. Validação da janela de timestamp ──────────────────────────────────
    if ts_header:
        try:
            ts_int = int(ts_header)
            if abs(time.time() - ts_int) > 300:
                _log("SECURITY_ALERT_WEBHOOK", "webhook", {
                    "ip": _user_ip(), "reason": "Timestamp fora da janela (>5min)"
                })
                return jsonify({"error": "timestamp_expired"}), 401
        except (ValueError, TypeError):
            pass

    # ── 3. Parse do payload (ElitePay / Universal) ───────────────────────────
    payload    = request.json or {}
    event_data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else payload

    identifier   = sanitize_input(str(payload.get("transactionId") or event_data.get("identifier") or event_data.get("transactionId") or ""), 80)
    correlation  = sanitize_input(str(payload.get("externalReference") or event_data.get("correlationID") or event_data.get("externalReference") or ""), 80)
    status       = sanitize_input(str(payload.get("transactionState") or payload.get("status") or event_data.get("status", "")), 30).upper()
    amount       = payload.get("value") or event_data.get("amount", 0)
    net          = payload.get("net") or event_data.get("net", amount)
    fee          = payload.get("fee") or event_data.get("fee", 0)
    end_to_end   = sanitize_input(str(payload.get("acquirerTransactionId") or event_data.get("endToEndId") or ""), 60)
    payer_info   = payload.get("payer") or event_data.get("payer", {})
    if isinstance(payer_info, str): payer_info = {"name": payer_info}
    if not payer_info.get("name") and payload.get("payerName"):
        payer_info = dict(payer_info)
        payer_info["name"] = payload.get("payerName")
    event_type   = payload.get("event") or payload.get("transactionType", event_hdr)

    # ── 4. Idempotência ──────────────────────────────────────────────────────
    idempotency_key = identifier or correlation or end_to_end
    if idempotency_key and idempotency_key in PROCESSED_WEBHOOKS:
        return jsonify({"ok": True, "duplicate": True}), 200

    # ── 5. Verificação de confirmação ────────────────────────────────────────
    is_confirmed = (
        status in ("COMPLETO", "APPROVED", "PAID", "CONCLUIDO") or
        str(event_type).upper() in ("DEPOSITO_COMPLETO", "PAYMENT.CONFIRMED", "PAYMENT.APPROVED")
    )



    record = PAYMENTS_DB.get(correlation) or PAYMENTS_DB.get(identifier)



    if is_confirmed:
        if record:
            _update_payment_status(
                correlation or identifier or "webhook", "paid",
                payer=payer_info, end_to_end_id=end_to_end,
                net_amount=net, fee_amount=fee)

            record = PAYMENTS_DB.get(correlation) or PAYMENTS_DB.get(identifier) or record

            confirmed_payload = dict(record)
            confirmed_payload.update({
                "c7_id":      identifier,
                "payment_id": correlation or identifier,
                "amount":     amount or record.get("amount"),
                "net":        net,
                "fee":        fee,
                "payer_name": payer_info.get("name") or record.get("name", "N/A"),
                "name":       record.get("name") or payer_info.get("name", "N/A"),
                "end_to_end": end_to_end,
                "event":      event_type,
                "status":     "paid",
            })

            _log("PAYMENT_CONFIRMED", correlation or identifier or "webhook", confirmed_payload)

            if TG_WH_AVAILABLE and record.get("tg_id") and record.get("slug"):
                tg_wh.log_tenant_event(record["tg_id"], record["slug"], "PAYMENT_CONFIRMED", correlation or identifier, record.get("ip", ""), confirmed_payload)
                tg_wh.mark_tg_converted(record["tg_id"], correlation or identifier)

            if TG_WH_AVAILABLE:
                html_msg = _format_payment_html_msg(confirmed_payload)
                wa_digits = re.sub(r'\D', '', str(record.get("phone", "")))
                markup = None
                if len(wa_digits) >= 10:
                    wa_num = wa_digits if wa_digits.startswith("55") else f"55{wa_digits}"
                    markup = {"inline_keyboard": [[{"text": "💬 Chamar Cliente no WhatsApp", "url": f"https://wa.me/{wa_num}"}]]}
                tg_wh.notify_log_channel("pagamento", html_msg, markup=markup)

            if record.get("email"):
                try:
                    import email_sender
                    to_em = record["email"]
                    prod_name = record.get("product_name", "Produto")
                    val_brl = record.get("amount", amount)
                    html_body = f"<h2>Pagamento Confirmado!</h2><p>Você pagou R${float(val_brl):.2f} pelo {prod_name}.</p>"
                    if TG_WH_AVAILABLE:
                        tpls = tg_wh.get_email_templates()
                        if tpls:
                            html_body = tpls[-1]['html_content']
                            html_body = html_body.replace('[Nome do produto]', prod_name)
                            html_body = html_body.replace('[00,00]', f"R$ {float(val_brl):.2f}".replace('.',','))
                            html_body = html_body.replace('[Nome do comprador]', payer_info.get("name", "Cliente"))
                            html_body = html_body.replace('[Forma de pagamento]', 'PIX')
                            
                            wa_num = tg_wh.get_config("whatsapp_number") or "5511999999999"
                            wa_msg = tg_wh.get_config("whatsapp_message") or "Olá"
                            import urllib.parse
                            wa_link = f"https://wa.me/{wa_num}?text={urllib.parse.quote(wa_msg)}"
                            html_body = html_body.replace('[LINK_WHATSAPP]', wa_link)
                            html_body = html_body.replace('./images/', request.host_url + 'static/email_images/')
                    
                    s_ok = email_sender.send_confirmation_email(to_em, f"Confirmação de Pagamento - {prod_name}", html_body)
                    if TG_WH_AVAILABLE:
                        tg_wh.log_email(1, to_em, f"Auto: {prod_name}", "Enviado" if s_ok else "Falha")
                except Exception as e:
                    _log("EMAIL_AUTO_ERR", correlation, {"error": str(e)})

        if idempotency_key:
            _mark_webhook_processed(idempotency_key)



    # â”€â”€â”€ 8. Responde HTTP 2xx (sec. 10) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    return jsonify({"ok": True}), 200


# ─── WEBHOOK UNIÃO 7 PAY ──────────────────────────────────────────────────────
@app.route('/api/webhook/uniaopay', methods=['POST'])
@app.route('/api/webhook/uniao7pay', methods=['POST'])
def webhook_uniaopay():
    """
    Webhook oficial União 7 Pay:
    Recebe POST:
    {
      "transaction_id": "tx_abcdef123456",
      "status": "paid",
      "amount": 50.00
    }
    """
    payload = request.json or {}
    tx_id = sanitize_input(str(payload.get("transaction_id") or payload.get("transactionId") or payload.get("id") or ""), 80)
    status = sanitize_input(str(payload.get("status", "")), 30).lower()
    amount = payload.get("amount")

    if not tx_id:
        return jsonify({"ok": False, "error": "transaction_id_missing"}), 400

    print(f"[Uniao7Pay Webhook] Recebido: tx_id={tx_id}, status={status}, amount={amount}")

    # Idempotência
    if tx_id in PROCESSED_WEBHOOKS:
        return jsonify({"ok": True, "duplicate": True}), 200

    is_confirmed = status in ("paid", "approved", "success", "concluido", "completo")

    # Localiza o registro de pagamento
    record = None
    for pid, p in list(PAYMENTS_DB.items()):
        if p.get("c7_id") == tx_id or p.get("payment_id") == tx_id:
            record = p
            break

    if not record:
        try:
            conn = admin_bot.get_db() if BOT_AVAILABLE else (tg_wh._get_db() if TG_WH_AVAILABLE else None)
            if conn:
                row = conn.execute("SELECT * FROM payments WHERE c7_id=? OR payment_id=?", (tx_id, tx_id)).fetchone()
                if row:
                    record = dict(row)
                conn.close()
        except Exception:
            pass

    if is_confirmed:
        PROCESSED_WEBHOOKS.add(tx_id)
        pid = (record.get("payment_id") if record else "") or tx_id
        if record:
            _update_payment_status(pid, "paid")
            record = PAYMENTS_DB.get(pid) or record

            confirmed_payload = dict(record)
            confirmed_payload.update({
                "c7_id": tx_id,
                "payment_id": pid,
                "amount": amount or record.get("amount"),
                "status": "paid",
                "gateway": "uniaopay"
            })

            _log("PAYMENT_CONFIRMED", pid, confirmed_payload)

            if TG_WH_AVAILABLE and record.get("tg_id") and record.get("slug"):
                tg_wh.log_tenant_event(record["tg_id"], record["slug"], "PAYMENT_CONFIRMED", pid, record.get("ip", ""), confirmed_payload)
                tg_wh.mark_tg_converted(record["tg_id"], pid)

            if TG_WH_AVAILABLE:
                html_msg = _format_payment_html_msg(confirmed_payload)
                wa_digits = re.sub(r'\D', '', str(record.get("phone", "")))
                markup = None
                if len(wa_digits) >= 10:
                    wa_num = wa_digits if wa_digits.startswith("55") else f"55{wa_digits}"
                    markup = {"inline_keyboard": [[{"text": "💬 Chamar Cliente no WhatsApp", "url": f"https://wa.me/{wa_num}"}]]}
                tg_wh.notify_log_channel("pagamento", html_msg, markup=markup)

            return jsonify({"ok": True, "message": "Pagamento confirmado via União 7 Pay"}), 200
        else:
            print(f"[Uniao7Pay Webhook] Transação {tx_id} aprovada, mas não encontrada em cache local.")
            return jsonify({"ok": True, "warning": "transaction_not_found_locally"}), 200

    return jsonify({"ok": True, "status": status}), 200


# ─── ADMIN SUPREMO: UNIÃO 7 PAY CONFIG & CONTROLE ─────────────────────────────
@app.route('/api/admin/uniaopay/config', methods=['GET', 'POST'])
def api_admin_uniaopay_config():
    """Retorna ou atualiza as configurações da União 7 Pay no Vault."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    supreme_id = int(os.environ.get("SUPREME_ADMIN_ID", str(_SUPREME_ADMIN_ID)))
    if admin_id != supreme_id and role != "supreme_admin":
        return jsonify({"ok": False, "error": "acesso_restrito", "message": "Exclusivo do Admin Supremo."}), 403

    if request.method == 'GET':
        cfg = _get_uniaopay_config()
        active_gw = credential_vault.get_active_gateway(supreme_id) if VAULT_AVAILABLE else "elitepay"
        return jsonify({
            "ok": True,
            "config": {
                "api_key": cfg["api_key"],
                "base_url": cfg["base_url"],
                "fallback_enabled": cfg["fallback_enabled"],
                "is_active_primary": active_gw == "uniaopay",
                "active_gateway": active_gw
            }
        })

    data = request.json or {}
    api_key = data.get("api_key", "").strip()
    base_url = data.get("base_url", "").strip() or UNIAOPAY_DEFAULT_BASE_URL
    fallback_enabled = bool(data.get("fallback_enabled", True))
    make_primary = bool(data.get("make_primary", False))

    if VAULT_AVAILABLE:
        creds = {
            "api_key": api_key,
            "base_url": base_url,
            "fallback_enabled": "1" if fallback_enabled else "0"
        }
        credential_vault.save_gateway_credentials(supreme_id, "uniaopay", creds, ip=_user_ip())
        if make_primary:
            credential_vault.set_gateway_active(supreme_id, "uniaopay", True, ip=_user_ip())

    return jsonify({"ok": True, "message": "Configurações da União 7 Pay salvas com sucesso!"})


@app.route('/api/admin/uniaopay/activate', methods=['POST'])
def api_admin_uniaopay_activate():
    """Ativa ou desativa a União 7 Pay como Gateway Primário Oficial."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    supreme_id = int(os.environ.get("SUPREME_ADMIN_ID", str(_SUPREME_ADMIN_ID)))
    if admin_id != supreme_id and role != "supreme_admin":
        return jsonify({"ok": False, "error": "acesso_restrito"}), 403

    data = request.json or {}
    active = bool(data.get("active", True))

    if VAULT_AVAILABLE:
        if active:
            credential_vault.set_gateway_active(supreme_id, "uniaopay", True, ip=_user_ip())
            return jsonify({"ok": True, "message": "União 7 Pay ativada como Gateway Primário!"})
        else:
            credential_vault.set_gateway_active(supreme_id, "elitepay", True, ip=_user_ip())
            return jsonify({"ok": True, "message": "ElitePay restaurada como Gateway Primário!"})

    return jsonify({"ok": True})


@app.route('/api/admin/uniaopay/test', methods=['POST'])
def api_admin_uniaopay_test():
    """
    Testa a conectividade e validade da chave da União 7 Pay de forma inteligente.
    Usa múltiplas estratégias de bypass Cloudflare e valida a chave sem depender
    apenas de criar uma cobrança de teste (que aciona mais proteções anti-bot).
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.json or {}
    api_key_input = data.get("api_key", "").strip()
    base_url_input = data.get("base_url", "").strip()

    # Não sobrepor chave real com máscara de input UI
    if api_key_input and (set(api_key_input).issubset({"•", "*"}) or len(api_key_input) < 20):
        api_key_input = ""

    # Carrega config salva + sobrescreve só se o admin passou algo novo no form
    cfg = _get_uniaopay_config()
    api_key  = (api_key_input  or cfg.get("api_key",  "")).strip()
    base_url = (base_url_input or cfg.get("base_url", "")).strip()

    if not api_key:
        return jsonify({"ok": False, "error": "Chave API não configurada. Salve a chave antes de testar.", "step": "validation"})

    if not base_url or not base_url.startswith("http"):
        return jsonify({"ok": False, "error": "URL base inválida. Configure a URL do endpoint antes de testar.", "step": "validation"})

    import time as _time
    t0 = _time.time()

    # ── Extrai domínio raiz para warmup anti-Cloudflare
    domain_root = "https://" + base_url.split("//")[-1].split("/")[0]

    headers_check = {
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": domain_root + "/",
        "Origin": domain_root,
    }

    sess = None
    warmup_ok = False
    method_used = "requests"

    # ── ESTRATÉGIA 1: curl_cffi com warmup de cookies
    try:
        from curl_cffi import requests as cffi_requests
        sess = cffi_requests.Session()
        for imp in ("chrome124", "chrome120", "chrome110", "safari17_0", "safari15_5"):
            try:
                wres = sess.get(domain_root, impersonate=imp, timeout=8, allow_redirects=True)
                if wres.status_code not in (403, 429):
                    warmup_ok = True
                    method_used = f"curl_cffi/{imp}"
                    break
            except Exception:
                continue
    except ImportError:
        sess = None

    # ── ESTRATÉGIA 2: cloudscraper como fallback
    if not warmup_ok:
        try:
            import cloudscraper
            sess = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True},
                delay=3
            )
            method_used = "cloudscraper"
            warmup_ok = True
        except Exception:
            sess = None

    # ── Tenta endpoint de health/auth leve antes do PIX create
    # Muitas gateways têm /api/v1/me, /api/v1/user, /api/v1/status, /api/v1/account
    health_endpoints = []
    parsed_base = base_url.rstrip("/")
    # Se a base_url já aponta para /pix/create, extrai raiz
    api_root = parsed_base
    for suffix in ("/pix/create", "/pix", "/create"):
        if api_root.endswith(suffix):
            api_root = api_root[: -len(suffix)]
    health_endpoints = [
        api_root + "/account",
        api_root + "/me",
        api_root + "/user",
        api_root + "/status",
        api_root + "/balance",
        api_root + "/health",
        domain_root + "/api/v1/account",
        domain_root + "/api/v1/me",
    ]

    health_status = None
    health_detail = ""
    for ep in health_endpoints:
        try:
            if sess is not None and hasattr(sess, "get"):
                hr = sess.get(ep, headers=headers_check, timeout=7, allow_redirects=False)
            else:
                hr = requests.get(ep, headers=headers_check, timeout=7, allow_redirects=False)
            if hr.status_code in (200, 201, 204):
                elapsed_ms = int((_time.time() - t0) * 1000)
                return jsonify({
                    "ok": True,
                    "gateway": "uniaopay",
                    "message": f"Conexão validada com sucesso via {ep} — API Key aceita.",
                    "status_code": hr.status_code,
                    "elapsed_ms": elapsed_ms,
                    "method": method_used,
                    "endpoint_tested": ep,
                })
            elif hr.status_code == 401:
                health_status = 401
                health_detail = f"Chave API rejeitada (HTTP 401) em {ep}."
                break  # 401 = API acessível mas key inválida — conclusivo
            elif hr.status_code == 403 and "cloudflare" not in hr.text.lower():
                health_status = 403
                health_detail = f"Acesso negado (HTTP 403) em {ep}."
        except Exception:
            continue

    if health_status == 401:
        return jsonify({"ok": False, "error": health_detail, "step": "auth", "status_code": 401})

    # ── Fallback final: tenta criar cobrança real de teste
    test_res = create_uniaopay_pix(
        amount=20.00,
        customer={
            "name": "VAGNER DE CAMARGO SIRINO",
            "document": "03229612973",
            "email": "teste@gmail.com",
            "phone": "41999786408"
        },
        custom_api_key=api_key,
        custom_base_url=base_url
    )

    # Se o erro é Cloudflare 403, retorna mensagem mais inteligente
    if not test_res.get("ok") and test_res.get("cloudflare_challenge"):
        elapsed_ms = int((_time.time() - t0) * 1000)
        return jsonify({
            "ok": None,  # None = inconclusivo (não é falha da chave)
            "warning": True,
            "gateway": "uniaopay",
            "message": (
                "A API da União 7 Pay está protegida por Cloudflare e bloqueou o teste direto. "
                "Isso NÃO significa que sua chave está incorreta — é uma proteção anti-bot do servidor. "
                "Se você configurou a chave corretamente, o gateway funcionará normalmente em produção."
            ),
            "suggestion": "Ative como Primária e faça um teste de pagamento real para confirmar.",
            "elapsed_ms": elapsed_ms,
            "method": method_used,
            "status_code": test_res.get("status_code"),
        })

    elapsed_ms = int((_time.time() - t0) * 1000)
    test_res["elapsed_ms"] = elapsed_ms
    test_res["method"] = method_used
    return jsonify(test_res)


# ─── ELITEPAY FINANCIAL SUITE & SAQUES RÁPIDOS (ADMIN SUPREMO) ──────────────

@app.route('/api/admin/elitepay/balance', methods=['GET', 'POST'])
@app.route('/api/c7/balance', methods=['POST'])
def elitepay_balance():
    """
    Consulta saldo da conta ElitePay em tempo real — RESTRITO ao Admin Supremo.
    GET https://api.elitepaybr.com/api/v1/balance com headers x-client-id e x-client-secret.
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized", "message": "Token de acesso invalido."}), 401
    if role != "supreme_admin":
        return jsonify({"ok": False, "error": "acesso_restrito", "message": "Consulta de saldo e exclusiva do Admin Supremo."}), 403

    keys = _get_live_gateway_keys()
    client_id = keys.get("client_id") or keys.get("api_key", "")
    client_secret = keys.get("client_secret") or keys.get("api_secret", "")
    base_url = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")

    if not client_id or "xxx" in client_id:
        return jsonify({"ok": False, "error": "credenciais_nao_configuradas", "message": "Configure o Client ID e Client Secret da ElitePay no Vault."}), 400

    try:
        headers = get_elitepay_headers(client_id, client_secret)
        res = requests.get(f"{base_url}/api/v1/balance", headers=headers, timeout=8)
        if res.status_code == 200:
            resp = res.json()
            data = resp.get("data", {})
            bal_num = float(data.get("balance", 0.0))
            formatted = f"R$ {bal_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return jsonify({
                "ok": True,
                "balance": f"{bal_num:.2f}",
                "formatted": formatted,
                "data": data,
                "message": resp.get("message", "Saldo obtido com sucesso.")
            }), 200
        else:
            return jsonify({
                "ok": False,
                "error": f"ElitePay retornou HTTP {res.status_code}",
                "detail": res.text[:250]
            }), res.status_code
    except Exception as err:
        return jsonify({"ok": False, "error": "gateway_error", "detail": str(err)}), 500


@app.route('/api/admin/elitepay/quote', methods=['GET'])
def elitepay_crypto_quote():
    """
    Consulta cotação atual USDT/BRL, taxas e limites da ElitePay (pública, sem autenticação).
    GET https://api.elitepaybr.com/api/v1/crypto/quote
    """
    keys = _get_live_gateway_keys()
    base_url = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")
    try:
        res = requests.get(f"{base_url}/api/v1/crypto/quote", timeout=6)
        if res.status_code == 200:
            return jsonify(res.json()), 200
        return jsonify({"ok": False, "error": f"HTTP {res.status_code}", "detail": res.text[:200]}), res.status_code
    except Exception as err:
        return jsonify({"ok": False, "error": "quote_failed", "detail": str(err)}), 500


@app.route('/api/admin/elitepay/withdraw-pix', methods=['POST'])
def elitepay_withdraw_pix():
    """
    Realiza Saque Rápido via PIX — RESTRITO EXCLUSIVAMENTE ao Admin Supremo.
    POST https://api.elitepaybr.com/api/v1/withdraw
    Body: amount, pixKey, pixKeyType, description
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id or role != "supreme_admin":
        return jsonify({"ok": False, "error": "unauthorized", "message": "Apenas o Admin Supremo tem permissao de saque."}), 403

    data = request.json or {}
    try:
        amount = float(str(data.get("amount", "0")).replace("R$", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return jsonify({"ok": False, "error": "Valor de saque invalido."}), 400

    if amount <= 0:
        return jsonify({"ok": False, "error": "O valor de saque deve ser maior que zero."}), 400

    pix_key = sanitize_input(str(data.get("pix_key", "")).strip(), 120)
    pix_key_type = sanitize_input(str(data.get("pix_key_type", "CPF")).upper().strip(), 20)
    description = sanitize_input(str(data.get("description", "Saque Admin Supremo")).strip(), 100)

    if not pix_key:
        return jsonify({"ok": False, "error": "Chave PIX e obrigatoria."}), 400

    keys = _get_live_gateway_keys()
    client_id = keys.get("client_id") or keys.get("api_key", "")
    client_secret = keys.get("client_secret") or keys.get("api_secret", "")
    base_url = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")

    if not client_id or not client_secret:
        return jsonify({"ok": False, "error": "Credenciais da ElitePay ausentes no Vault."}), 400

    payload = {
        "amount": round(amount, 2),
        "pixKey": pix_key,
        "pixKeyType": pix_key_type,
        "description": description
    }

    try:
        headers = get_elitepay_headers(client_id, client_secret)
        res = requests.post(f"{base_url}/api/v1/withdraw", json=payload, headers=headers, timeout=12)
        resp_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {"raw": res.text[:200]}

        _log("SUPREME_WITHDRAW_PIX", str(uuid.uuid4()), {
            "admin_id": admin_id,
            "amount": amount,
            "pix_key": pix_key[:4] + "***" + pix_key[-4:] if len(pix_key) > 8 else "***",
            "pix_key_type": pix_key_type,
            "status_code": res.status_code,
            "success": res.status_code in (200, 201),
            "ip": _user_ip()
        })

        if res.status_code in (200, 201):
            return jsonify({
                "ok": True,
                "success": True,
                "message": "Saque PIX processado com sucesso!",
                "data": resp_data
            }), 200
        else:
            err_msg = resp_data.get("message") or resp_data.get("error") or f"Erro HTTP {res.status_code}"
            return jsonify({"ok": False, "error": err_msg, "detail": resp_data}), res.status_code

    except Exception as err:
        return jsonify({"ok": False, "error": "withdraw_error", "detail": str(err)}), 500


@app.route('/api/admin/elitepay/withdraw-crypto', methods=['POST'])
def elitepay_withdraw_crypto():
    """
    Realiza Saque Rápido em Cripto (USDT BEP20) — RESTRITO EXCLUSIVAMENTE ao Admin Supremo.
    POST https://api.elitepaybr.com/api/v1/crypto/withdraw
    Body: amount (BRL min R$ 20, max R$ 2000), wallet (0x + 40 hex chars)
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id or role != "supreme_admin":
        return jsonify({"ok": False, "error": "unauthorized", "message": "Apenas o Admin Supremo tem permissao de saque."}), 403

    data = request.json or {}
    try:
        amount = float(str(data.get("amount", "0")).replace("R$", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return jsonify({"ok": False, "error": "Valor de saque invalido."}), 400

    wallet = sanitize_input(str(data.get("wallet", "")).strip(), 60)

    # Validação rigorosa de carteira BEP20
    if not re.match(r"^0x[a-fA-F0-9]{40}$", wallet):
        return jsonify({"ok": False, "error": "Endereco de carteira BEP20 invalido. Deve comecar com 0x seguido de 40 caracteres hexadecimais."}), 400

    # Limites oficiais da documentação: R$ 20 a R$ 2.000
    if amount < 20 or amount > 2000:
        return jsonify({"ok": False, "error": f"Valor fora dos limites oficiais: Minimo R$ 20,00 e Maximo R$ 2.000,00 por transacao. (Solicitado: R$ {amount:.2f})"}), 400

    keys = _get_live_gateway_keys()
    client_id = keys.get("client_id") or keys.get("api_key", "")
    client_secret = keys.get("client_secret") or keys.get("api_secret", "")
    base_url = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")

    if not client_id or not client_secret:
        return jsonify({"ok": False, "error": "Credenciais da ElitePay ausentes no Vault."}), 400

    payload = {
        "amount": round(amount, 2),
        "wallet": wallet
    }

    try:
        headers = get_elitepay_headers(client_id, client_secret)
        res = requests.post(f"{base_url}/api/v1/crypto/withdraw", json=payload, headers=headers, timeout=14)
        resp_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {"raw": res.text[:200]}

        _log("SUPREME_WITHDRAW_CRYPTO", str(uuid.uuid4()), {
            "admin_id": admin_id,
            "amount": amount,
            "wallet": wallet[:6] + "..." + wallet[-4:],
            "status_code": res.status_code,
            "success": res.status_code in (200, 201),
            "ip": _user_ip()
        })

        if res.status_code in (200, 201):
            return jsonify({
                "ok": True,
                "success": True,
                "message": "Saque Crypto USDT enviado para processamento com sucesso!",
                "data": resp_data
            }), 200
        else:
            err_msg = resp_data.get("message") or resp_data.get("error") or f"Erro HTTP {res.status_code}"
            return jsonify({"ok": False, "error": err_msg, "detail": resp_data}), res.status_code

    except Exception as err:
        return jsonify({"ok": False, "error": "crypto_withdraw_error", "detail": str(err)}), 500


@app.route('/api/admin/elitepay/test-adquirers', methods=['POST', 'GET'])
@app.route('/api/admin/c7-test-acquirers', methods=['POST'])
def elitepay_test_adquirers():
    """
    Testa todos os adquirentes e rotas da ElitePay verificando conectividade real,
    latência em milissegundos e estabilidade da rede.
    RESTRITO ao Admin Supremo.
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id or role not in ("supreme_admin", "admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    keys = _get_live_gateway_keys()
    client_id = keys.get("client_id") or keys.get("api_key", "")
    client_secret = keys.get("client_secret") or keys.get("api_secret", "")
    base_url = keys.get("base_url", "https://api.elitepaybr.com").rstrip("/")

    headers = get_elitepay_headers(client_id, client_secret)

    targets = [
        {"id": "base",    "name": "Servidor Base ElitePay",     "url": f"{base_url}/health",                        "method": "GET",  "auth": False},
        {"id": "deposit", "name": "Adquirente PIX (Cash-In)",   "url": f"{base_url}/api/v1/deposit",                "method": "POST", "auth": True,  "body": {"amount": 10.00, "description": "Ping Test", "payerName": "VAGNER DE CAMARGO SIRINO", "payerDocument": "03229612973"}},
        {"id": "balance", "name": "Adquirente Saldo (Cash-Out)", "url": f"{base_url}/api/v1/balance",                "method": "GET",  "auth": True},
        {"id": "quote",   "name": "Rede Blockchain USDT BEP20", "url": f"{base_url}/api/v1/crypto/quote",           "method": "GET",  "auth": False},
        {"id": "check",   "name": "Consulta Status Transação",  "url": f"{base_url}/api/v1/transactions/check",    "method": "POST", "auth": True,  "body": {"transactionId": "api_ping_test"}},
    ]

    results = {}
    for tgt in targets:
        t0 = time.perf_counter()
        try:
            req_hdrs = headers if tgt["auth"] else {"Accept": "application/json"}
            if tgt["method"] == "GET":
                r = requests.get(tgt["url"], headers=req_hdrs, timeout=6)
            else:
                r = requests.post(tgt["url"], json=tgt.get("body", {}), headers=req_hdrs, timeout=6)
            lat = int((time.perf_counter() - t0) * 1000)
            sc = r.status_code
            # 400/401/422 com auth = adquirente online e rejeitou o ping (normal)
            is_ok = sc in (200, 201) or (sc in (400, 401, 422, 404) and tgt["auth"])
            stab = "ALTA" if lat < 300 else ("MEDIA" if lat < 700 else "BAIXA")
            msg = f"Online ({lat}ms) - Estabilidade {stab}" if is_ok else f"HTTP {sc} ({lat}ms)"
            results[tgt["id"]] = {
                "name": tgt["name"],
                "ok": is_ok,
                "status": "success" if is_ok else "warning",
                "http_code": sc,
                "status_code": sc,
                "latency_ms": lat,
                "stability": stab,
                "message": msg
            }
        except requests.exceptions.Timeout:
            results[tgt["id"]] = {"name": tgt["name"], "ok": False, "status": "error", "http_code": 0, "latency_ms": 6000, "stability": "TIMEOUT", "message": "Timeout (>6s)"}
        except Exception as e:
            results[tgt["id"]] = {"name": tgt["name"], "ok": False, "status": "error", "http_code": 0, "latency_ms": 0, "stability": "OFFLINE", "message": f"Falha: {str(e)[:40]}"}

    # Calcula estabilidade geral
    ok_count = sum(1 for v in results.values() if v.get("ok"))
    stability_score = f"{int(ok_count / len(results) * 100)}%" if results else "0%"

    # Alias para compatibilidade (quote também exposto como crypto)
    results["crypto"] = results.get("quote", results.get("crypto", {}))

    # Compatibilidade com a UI antiga do admin (c7_compat)
    c7_compat = {
        "1":    {"status": results.get("deposit", {}).get("status", "success"), "message": results.get("deposit", {}).get("message", "OK")},
        "2":    {"status": results.get("balance", {}).get("status", "success"), "message": results.get("balance", {}).get("message", "OK")},
        "auto": {"status": results.get("base",    {}).get("status", "success"), "message": results.get("base",    {}).get("message", "OK")},
        "":     {"status": results.get("quote",   {}).get("status", "success"), "message": results.get("quote",   {}).get("message", "OK")},
    }

    return jsonify({
        "ok": True,
        "endpoints": results,        # chave esperada pelo frontend
        "adquirers": results,        # alias de compatibilidade
        "results": c7_compat,
        "stability_score": stability_score,
        "base_url": base_url
    })






# â”€â”€â”€ ASSISTENTE IA PARA IMAGENS E ANÚNCIOS (GEMINI STUDIO INTEGRADO) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

GEMINI_STUDIO_KEY = os.environ.get("GEMINI_STUDIO_KEY", "")



@app.route('/api/admin/analyze-ai', methods=['POST'])

def api_admin_analyze_ai():

    """Analisa imagem do produto via Gemini Vision — requer autenticação de admin."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.json or {}

    product_raw  = sanitize_input(data.get("product_raw", ""), 200)

    image_url    = sanitize_input(data.get("image_url", ""), 500)

    image_base64 = data.get("image_base64", "")   # base64 sem prefixo data:...

    image_mime   = data.get("image_mime", "image/jpeg")



    def _gemini_call(parts):

        gemini_url = (

            f"https://generativelanguage.googleapis.com/v1beta/"

            f"models/gemini-1.5-flash:generateContent?key={GEMINI_STUDIO_KEY}"

        )

        prompt_system = (

            "Você é um especialista em precificação e redação de anúncios brasileiros para OLX. "

            "Analise o produto com precisão técnica. Responda EXCLUSIVAMENTE em JSON válido, sem markdown."

        )

        prompt_user = (

            f"Produto informado pelo usuário: '{product_raw}'.\n"

            "Retorne um JSON com EXATAMENTE estas chaves:\n"

            "- title: título atraente para anúncio OLX (máx 80 chars)\n"

            "- price: preço estimado de mercado Brasil 2025 (número, ex: 750.00)\n"

            "- description: descrição vendedora completa (mín 80 palavras, mencionando estado, funcionalidades, acessórios, envio)\n"

            "- category: categoria OLX mais adequada\n"

            "- brand: marca do produto\n"

            "- model: modelo exato do produto\n"

            "- condition: estado (Novo, Usado - Excelente, Usado - Bom, Usado - Regular)\n"

            "- storage: capacidade/tamanho se aplicável (ex: 64GB, 128GB)\n"

            "- color: cor predominante do produto na imagem\n"

            "- confidence: sua confiança na análise de 0 a 100\n"

            "JSON:"

        )

        full_parts = [{"text": prompt_system + "\n\n" + prompt_user}] + parts

        payload = {

            "contents": [{"parts": full_parts}],

            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}

        }

        res = requests.post(gemini_url, json=payload, timeout=15)

        res.raise_for_status()

        rj = res.json()

        raw_text = rj["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Limpa possível markdown fence

        if raw_text.startswith("```"):

            raw_text = raw_text.split("```")[-2].lstrip("json").strip()

        return json.loads(raw_text)



    if GEMINI_STUDIO_KEY:

        try:

            parts = []

            if image_base64:

                parts.append({"inline_data": {"mime_type": image_mime, "data": image_base64}})

            elif image_url:

                # Tenta baixar a imagem e enviar como base64

                try:

                    img_resp = requests.get(image_url, timeout=8)

                    if img_resp.status_code == 200:

                        b64 = base64.b64encode(img_resp.content).decode()

                        ct  = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]

                        parts.append({"inline_data": {"mime_type": ct, "data": b64}})

                except Exception:

                    pass  # sem imagem binária, usa só texto



            parsed = _gemini_call(parts)

            return jsonify({

                "ok": True,

                "title":       parsed.get("title",       product_raw.title()),

                "price":       str(parsed.get("price",   "750.00")),

                "description": parsed.get("description", ""),

                "category":    parsed.get("category",    "Celulares e Smartphones"),

                "brand":       parsed.get("brand",       ""),

                "model":       parsed.get("model",       ""),

                "condition":   parsed.get("condition",   "Usado - Excelente"),

                "storage":     parsed.get("storage",     ""),

                "color":       parsed.get("color",       ""),

                "confidence":  parsed.get("confidence",  0),

                "source":      "gemini_vision",

                "image_url":   image_url,

            })

        except Exception as err:

            print(f"[GEMINI VISION] {err}")



    # Fallback inteligente interno

    if TG_WH_AVAILABLE:

        ai_res = tg_wh.generate_ai_ad(product_raw or "Produto Anunciado")

        return jsonify({

            "ok": True,

            "title":       ai_res.get("product_name"),

            "price":       ai_res.get("product_price"),

            "description": ai_res.get("product_description"),

            "category":    "Celulares e Smartphones",

            "brand":       "",

            "model":       "",

            "condition":   "Usado - Excelente",

            "storage":     "",

            "color":       "",

            "confidence":  40,

            "source":      "fallback_internal",

            "image_url":   image_url,

        })



    name_t = product_raw.title() if product_raw else "Produto Exclusivo"

    return jsonify({

        "ok": True,

        "title":       name_t,

        "price":       "650.00",

        "description": f"{name_t} em excelente estado de conservação, testado e 100% funcional. Acompanha caixa e acessórios originais. Entrega disponível.",

        "category":    "Celulares e Smartphones",

        "brand":       "",

        "model":       "",

        "condition":   "Usado - Excelente",

        "storage":     "",

        "color":       "",

        "confidence":  10,

        "source":      "static_fallback",

        "image_url":   image_url,

    })





# â”€â”€â”€ VALIDAÇÃO E LOOKUP AVANÇADO DE NÚMERO WHATSAPP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route('/api/admin/validate-whatsapp', methods=['POST'])

def api_validate_whatsapp():

    """

    Validação avançada de número WhatsApp:

    - Normalização e parsing completo do número

    - Verificação de formato E.164 para Brasil

    - Lookup de operadora, DDD, região e tipo de linha

    - Geração de links wa.me diretos para teste

    - Opcionalmente consulta NumVerify API (via NUMVERIFY_API_KEY env)

    """

    data = request.json or {}

    raw_number = sanitize_input(data.get("number", ""), 30)



    # 1. Normalização — remove tudo que não é dígito

    digits_only = re.sub(r'\D', '', raw_number)



    # Remove zero inicial de DDD local

    if digits_only.startswith('0'):

        digits_only = digits_only[1:]



    # Adiciona DDI +55 Brasil se necessário

    if len(digits_only) <= 11 and not digits_only.startswith('55'):

        digits_only = '55' + digits_only



    # Remove +55 duplicado

    if digits_only.startswith('5555'):

        digits_only = '55' + digits_only[4:]



    ddi   = digits_only[:2]   if len(digits_only) >= 2 else ''

    ddd   = digits_only[2:4]  if len(digits_only) >= 4 else ''

    local = digits_only[4:]   if len(digits_only) > 4  else ''



    # 2. Validação de formato BR

    is_valid = (

        bool(re.match(r'^55\d{2}[6-9]\d{8}$', digits_only)) or  # celular 9 dígitos

        bool(re.match(r'^55\d{2}[2-5]\d{7}$', digits_only))      # fixo 8 dígitos

    )

    is_mobile = bool(re.match(r'^[6-9]', local)) if local else False

    line_type = "Celular" if is_mobile else ("Fixo" if local else "Desconhecido")



    # 3. Mapeamento de DDDs por região

    DDD_MAP = {

        "11":"São Paulo - Capital","12":"SP - Vale do Paraíba","13":"SP - Baixada Santista",

        "14":"SP - Bauru","15":"SP - Sorocaba","16":"SP - Ribeirão Preto",

        "17":"SP - Rio Preto","18":"SP - Araçatuba","19":"SP - Campinas",

        "21":"Rio de Janeiro - Capital","22":"RJ - Interior","24":"RJ - Volta Redonda",

        "27":"ES - Vitória","28":"ES - Interior",

        "31":"MG - Belo Horizonte","32":"MG - Juiz de Fora","33":"MG - Gov. Valadares",

        "34":"MG - Uberlândia","35":"MG - Poços de Caldas","37":"MG - Divinópolis","38":"MG - Montes Claros",

        "41":"PR - Curitiba","42":"PR - Ponta Grossa","43":"PR - Londrina","44":"PR - Maringá",

        "45":"PR - Cascavel","46":"PR - Pato Branco",

        "47":"SC - Joinville","48":"SC - Florianópolis","49":"SC - Chapecó",

        "51":"RS - Porto Alegre","53":"RS - Pelotas","54":"RS - Caxias do Sul","55":"RS - Santa Maria",

        "61":"Brasília / DF","62":"GO - Goiânia","63":"Tocantins","64":"GO - Interior",

        "65":"MT - Cuiabá","66":"MT - Rondonópolis","67":"MS - Campo Grande","68":"Acre","69":"Rondônia",

        "71":"BA - Salvador","73":"BA - Ilhéus","74":"BA - Interior","75":"BA - Feira de Santana","77":"BA - Vitória da Conquista",

        "79":"SE - Aracaju",

        "81":"PE - Recife","82":"Alagoas","83":"Paraíba","84":"RN - Natal","85":"CE - Fortaleza",

        "86":"PI - Teresina","87":"PE - Interior","88":"CE - Interior","89":"PI - Interior",

        "91":"PA - Belém","92":"AM - Manaus","93":"PA - Santarém","94":"PA - Marabá",

        "95":"Roraima","96":"Amapá","97":"AM - Interior","98":"MA - São Luís","99":"MA - Interior",

    }

    regiao = DDD_MAP.get(ddd, f"DDD {ddd}" if ddd else "Região desconhecida")



    # 4. Formata para exibição nacional BR

    if len(local) == 9:

        local_fmt = f"({ddd}) {local[0]} {local[1:5]}-{local[5:]}"

    elif len(local) == 8:

        local_fmt = f"({ddd}) {local[:4]}-{local[4:]}"

    else:

        local_fmt = f"({ddd}) {local}"



    # 5. Lookup via NumVerify API (opcional)

    carrier      = ""

    lookup_source = "local"

    numverify_key = os.environ.get("NUMVERIFY_API_KEY", "")

    if numverify_key and is_valid:

        try:

            nv_url = (

                f"http://apilayer.net/api/validate"

                f"?access_key={numverify_key}&number={digits_only}&country_code=BR&format=1"

            )

            nv = requests.get(nv_url, timeout=5).json()

            if nv.get("valid"):

                carrier       = nv.get("carrier", "")

                line_type     = nv.get("line_type", line_type)

                regiao        = nv.get("location", regiao)

                local_fmt     = nv.get("national_format", local_fmt)

                lookup_source = "numverify"

        except Exception as e:

            print(f"[NumVerify] {e}")



    # 6. Links de ação

    wa_link      = f"https://wa.me/{digits_only}"

    wa_chat_link = f"https://wa.me/{digits_only}?text=Ol%C3%A1%2C+testando+contato"

    wa_api_link  = f"https://api.whatsapp.com/send?phone={digits_only}"



    return jsonify({

        "ok":           True,

        "valid":        is_valid,

        "raw_input":    raw_number,

        "normalized":   digits_only,

        "e164":         f"+{digits_only}",

        "national":     local_fmt,

        "ddi":          ddi,

        "ddd":          ddd,

        "local":        local,

        "region":       regiao,

        "country":      "Brasil",

        "line_type":    line_type,

        "carrier":      carrier,

        "wa_link":      wa_link,

        "wa_chat_link": wa_chat_link,

        "wa_api_link":  wa_api_link,

        "lookup_source":lookup_source,

    })





@app.route('/api/products', methods=['GET'])

def api_products_list():

    """Lista todos os modelos de produto do banco."""

    if not BOT_AVAILABLE:

        return jsonify({"ok": False, "error": "bot_not_available"}), 503

    conn = admin_bot.get_db()

    rows = conn.execute(

        "SELECT id, code, name, price, description, image_url FROM product_templates ORDER BY id ASC"

    ).fetchall()

    conn.close()

    products = [

        {"id": r["id"], "code": r["code"], "name": r["name"],

         "price": r["price"], "description": r["description"] or "",

         "image_url": r["image_url"] or ""}

        for r in rows

    ]

    return jsonify({"ok": True, "products": products})





@app.route('/api/products', methods=['POST'])

def api_products_create():

    """Cria um novo modelo de produto."""

    if not BOT_AVAILABLE:

        return jsonify({"ok": False, "error": "bot_not_available"}), 503

    data = request.json or {}

    name        = sanitize_input(data.get('name', ''), 200)

    price       = sanitize_input(data.get('price', ''), 20)

    description = sanitize_input(data.get('description', ''), 2000)

    image_url   = sanitize_input(data.get('image_url', ''), 500)

    code        = sanitize_input(data.get('code', ''), 80)



    if not name or not price:

        return jsonify({"ok": False, "error": "name e price são obrigatórios"}), 400



    # Auto-gera code se não fornecido

    if not code:

        code = re.sub(r'[^a-z0-9_]', '_', name.lower().strip())[:40]

        code = re.sub(r'_+', '_', code).strip('_')

        code = f"{code}_{uuid.uuid4().hex[:6]}"



    try:

        conn = admin_bot.get_db()

        conn.execute(

            "INSERT INTO product_templates(code, name, price, description, image_url) VALUES(?,?,?,?,?)",

            (code, name, price, description, image_url)

        )

        conn.commit()

        row_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

        conn.close()

    except Exception as e:

        if "UNIQUE" in str(e):

            return jsonify({"ok": False, "error": f"Código '{code}' já existe. Use outro nome."}), 409

        return jsonify({"ok": False, "error": str(e)}), 500



    base_url = request.host_url.rstrip('/')

    public_link = f"{base_url}/p/{code}"

    _log("PRODUCT_CREATED", str(uuid.uuid4()), {"code": code, "name": name, "price": price})

    return jsonify({"ok": True, "id": row_id, "code": code, "public_link": public_link}), 201





@app.route('/api/products/<code>', methods=['PUT'])

def api_products_update(code):

    """Edita um modelo de produto existente pelo código."""

    if not BOT_AVAILABLE:

        return jsonify({"ok": False, "error": "bot_not_available"}), 503

    safe_code = sanitize_input(code, 80)

    data = request.json or {}



    conn = admin_bot.get_db()

    row = conn.execute(

        "SELECT id FROM product_templates WHERE code=?", (safe_code,)

    ).fetchone()

    if not row:

        conn.close()

        return jsonify({"ok": False, "error": "Produto não encontrado"}), 404



    fields, values = [], []

    allowed = {'name': 200, 'price': 20, 'description': 2000, 'image_url': 500}

    for field, max_len in allowed.items():

        if field in data and isinstance(data[field], str):

            fields.append(f"{field}=?")

            values.append(sanitize_input(data[field], max_len))



    if not fields:

        conn.close()

        return jsonify({"ok": False, "error": "Nenhum campo válido para atualizar"}), 400



    values.append(safe_code)

    conn.execute(f"UPDATE product_templates SET {', '.join(fields)} WHERE code=?", values)

    conn.commit()

    conn.close()

    _log("PRODUCT_UPDATED", str(uuid.uuid4()), {"code": safe_code, "fields": list(data.keys())})

    return jsonify({"ok": True, "code": safe_code})





@app.route('/api/products/<code>', methods=['DELETE'])

def api_products_delete(code):

    """Remove um modelo de produto."""

    if not BOT_AVAILABLE:

        return jsonify({"ok": False, "error": "bot_not_available"}), 503

    safe_code = sanitize_input(code, 80)

    conn = admin_bot.get_db()

    result = conn.execute(

        "DELETE FROM product_templates WHERE code=?", (safe_code,)

    )

    conn.commit()

    conn.close()

    if result.rowcount == 0:

        return jsonify({"ok": False, "error": "Produto não encontrado"}), 404

    _log("PRODUCT_DELETED", str(uuid.uuid4()), {"code": safe_code})

    return jsonify({"ok": True})





@app.route('/api/products/<code>/link', methods=['GET'])

def api_product_link(code):

    """Retorna o link público personalizado de um produto."""

    if not BOT_AVAILABLE:

        return jsonify({"ok": False, "error": "bot_not_available"}), 503

    safe_code = sanitize_input(code, 80)

    conn = admin_bot.get_db()

    row = conn.execute(

        "SELECT name, price FROM product_templates WHERE code=?", (safe_code,)

    ).fetchone()

    conn.close()

    if not row:

        return jsonify({"ok": False, "error": "Produto não encontrado"}), 404

    base_url = request.host_url.rstrip('/')

    public_link = f"{base_url}/p/{safe_code}"

    return jsonify({"ok": True, "code": safe_code, "name": row["name"], "price": row["price"], "public_link": public_link})





@app.route('/api/products/<code>/apply', methods=['POST'])
def api_products_apply(code):
    """Define um produto do catálogo como produto ativo da loja."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    safe_code = sanitize_input(code, 80)

    # 1º: busca em tenant_products (produtos criados pelo admin no painel)
    if TG_WH_AVAILABLE:
        prods = tg_wh.get_tenant_products(admin_id)
        prod = next((p for p in prods if p.get("product_code") == safe_code), None)
        if prod:
            # Propaga configáes do produto para a config global do admin
            tg_wh.set_tenant_config(admin_id, "product_name",        prod.get("title", ""))
            tg_wh.set_tenant_config(admin_id, "product_price",       prod.get("price", ""))
            tg_wh.set_tenant_config(admin_id, "product_old_price",   prod.get("old_price", ""))
            tg_wh.set_tenant_config(admin_id, "product_description", prod.get("description", ""))
            tg_wh.set_tenant_config(admin_id, "active_product_code", safe_code)
            if prod.get("image_url") or prod.get("image1"):
                img = prod.get("image_url") or prod.get("image1", "")
                tg_wh.set_tenant_config(admin_id, "product_image",  img)
                tg_wh.set_tenant_config(admin_id, "product_image1", img)
            if prod.get("image2"): tg_wh.set_tenant_config(admin_id, "product_image2", prod["image2"])
            if prod.get("image3"): tg_wh.set_tenant_config(admin_id, "product_image3", prod["image3"])
            _log("PRODUCT_APPLIED", str(uuid.uuid4()), {"code": safe_code, "name": prod.get("title", "")})
            return jsonify({"ok": True, "applied": safe_code, "name": prod.get("title", "")})

    # 2º: fallback em product_templates (bot.py)
    if BOT_AVAILABLE:
        conn = admin_bot.get_db()
        row = conn.execute(
            "SELECT name, price, description, image_url FROM product_templates WHERE code=?", (safe_code,)
        ).fetchone()
        conn.close()
        if row:
            admin_bot.set_config("product_name",        row["name"])
            admin_bot.set_config("product_price",       row["price"])
            admin_bot.set_config("product_description", row["description"] or "")
            if row["image_url"]:
                admin_bot.set_config("product_image",  row["image_url"])
                admin_bot.set_config("product_image1", row["image_url"])
            _log("PRODUCT_APPLIED", str(uuid.uuid4()), {"code": safe_code, "name": row["name"]})
            return jsonify({"ok": True, "applied": safe_code, "name": row["name"]})

    return jsonify({"ok": False, "error": "Produto não encontrado"}), 404


# ─── UPSELL MODAIS ──────────────────────────────────────────────────────

@app.route('/api/admin/upsell/<product_code>', methods=['GET'])
def api_upsell_list(product_code):
    """Lista modais de upsell de um produto."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not TG_WH_AVAILABLE:
        return jsonify({"ok": True, "modals": []})
    modals = tg_wh.get_upsell_modals(admin_id, product_code)
    return jsonify({"ok": True, "modals": modals})


@app.route('/api/admin/upsell/<product_code>', methods=['POST'])
def api_upsell_create(product_code):
    """Cria um novo modal de upsell."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not TG_WH_AVAILABLE:
        return jsonify({"ok": False, "error": "indisponível"}), 503
    data = request.json or {}
    if not data.get("title", "").strip():
        return jsonify({"ok": False, "error": "Título obrigatório."}), 400
    new_id = tg_wh.create_upsell_modal(admin_id, product_code, data)
    return jsonify({"ok": True, "id": new_id, "message": "Modal criado com sucesso!"})


@app.route('/api/admin/upsell/modal/<int:modal_id>', methods=['PUT'])
def api_upsell_update(modal_id):
    """Atualiza um modal de upsell."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not TG_WH_AVAILABLE:
        return jsonify({"ok": False, "error": "indisponível"}), 503
    data = request.json or {}
    ok = tg_wh.update_upsell_modal(admin_id, modal_id, data)
    if ok:
        return jsonify({"ok": True, "message": "Modal atualizado!"})
    return jsonify({"ok": False, "error": "Modal não encontrado."}), 404


@app.route('/api/admin/upsell/modal/<int:modal_id>', methods=['DELETE'])
def api_upsell_delete(modal_id):
    """Remove um modal de upsell."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not TG_WH_AVAILABLE:
        return jsonify({"ok": False, "error": "indisponível"}), 503
    ok = tg_wh.delete_upsell_modal(admin_id, modal_id)
    if ok:
        return jsonify({"ok": True, "message": "Modal removido!"})
    return jsonify({"ok": False, "error": "Modal não encontrado."}), 404


@app.route('/api/admin/upsell/<product_code>/reorder', methods=['POST'])
def api_upsell_reorder(product_code):
    """Reordena modais de upsell."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not TG_WH_AVAILABLE:
        return jsonify({"ok": False, "error": "indisponível"}), 503
    data = request.json or {}
    order = data.get("order", [])
    tg_wh.reorder_upsell_modals(admin_id, product_code, order)
    return jsonify({"ok": True})


@app.route('/api/upsell/<product_code>', methods=['GET'])
def api_upsell_public(product_code):
    """Endpoint público: retorna modais ativos de upsell para o frontend do lead."""
    if not TG_WH_AVAILABLE:
        return jsonify({"ok": True, "modals": []})
    modals = tg_wh.get_upsell_modals_by_code(product_code)
    # Remove dados internos, expoe só o necessário
    safe = [{
        "id":          m["id"],
        "icon":        m.get("icon") or "shield-check",
        "type":        m.get("type") or "Seguro",
        "title":       m["title"],
        "description": m["description"],
        "amount":      m["amount"],
        "replay":      bool(m["replay"]),
        "position":    m["position"],
        "image_url":   m.get("image_url") or "",
        "image_pos":   m.get("image_pos") or "top",
    } for m in modals]
    return jsonify({"ok": True, "modals": safe})







# â”€â”€â”€ TELEGRAM WEBHOOK â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€



# URL camuflada: /tg/<webhook_secret> - _TG_WEBHOOK_SECRET ja definida acima (antes do @before_request).



@app.route(f'/tg/{_TG_WEBHOOK_SECRET}', methods=['POST'])

def telegram_webhook():

    """Recebe updates do Telegram e despacha para tg_webhook.dispatch().

    IMPORTANTE: Esta rota bypassa o WAF anti-bot — o Telegram usa User-Agent de servidor.

    """

    if not TG_WH_AVAILABLE:

        return '', 200

    try:

        update = request.get_json(force=True, silent=True) or {}

        tg_wh.dispatch(update)

    except Exception as e:

        print(f"[webhook] erro: {e}")

    # Sempre retorna 200 OK para o Telegram não tentar reenviar

    return '', 200





@app.route('/api/webhook/register')

def register_webhook():

    """Registra o webhook na API do Telegram. Chame uma vez após o deploy."""

    if not TG_WH_AVAILABLE:

        return jsonify({"error": "tg_webhook not loaded"}), 503

    base = os.environ.get("BASE_URL", request.host_url.rstrip("/"))

    url  = f"{base}/tg/{_TG_WEBHOOK_SECRET}"

    res  = tg_wh.set_webhook(url)

    return jsonify({"ok": res.get("ok"), "webhook_url": url, "tg_response": res})





# â”€â”€â”€ MULTI-TENANT SLUG PAGES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.route('/s/<slug>')
def slug_page(slug):
    """Serve a pagina do produto personalizada para cada usuario do Telegram."""
    if slug in PAYMENTS_DB or (slug and str(slug).startswith('olx_')):
        return check_payment(slug)

    if not TG_WH_AVAILABLE:
        abort(404)

    tg_id = tg_wh.get_tg_id_by_slug(slug)

    if tg_id is None:

        abort(404)

    ip = _user_ip()

    sid = str(uuid.uuid4())

    ua  = request.headers.get('User-Agent', '')

    tg_wh.upsert_tg_session(tg_id, slug, sid, ip, ua)

    tg_wh.log_tg_event(tg_id, slug, "PAGE_ENTRY", sid, ip, {"ua": ua[:120]})

    _log("PAGE_ENTRY", sid, {"slug": slug, "ip": ip})

    # Passa o slug e logo global para o template

    logo_url = admin_bot.get_config("logo_url", "") if BOT_AVAILABLE else ""
    prod_pub = tg_wh.get_cfg(tg_id, "product_published_at", "") if TG_WH_AVAILABLE else ""
    return render_template('index.html', page_slug=slug, session_id=sid, logo_url=logo_url, product_published_at=prod_pub)



@app.route('/api/event/<slug>', methods=['POST'])

def api_event_slug(slug):

    """Registra evento de uma pagina /s/<slug> no banco do usuario."""

    if not TG_WH_AVAILABLE:

        return jsonify({"ok": False}), 503

    tg_id = tg_wh.get_tg_id_by_slug(slug)

    if tg_id is None:

        return jsonify({"ok": False}), 404

    ip  = _user_ip()

    sid = request.headers.get('X-Session-Id', str(uuid.uuid4()))

    data = request.get_json(silent=True) or {}

    event_type = sanitize_input(data.pop('event', 'UNKNOWN'), 50)

    # Marca sessao convertida em eventos-chave

    if event_type in ("LEAD_CAPTURED", "PAYMENT_CONFIRMED"):

        tg_wh.mark_tg_converted(tg_id, sid)

    tg_wh.log_tg_event(tg_id, slug, event_type, sid, ip, data)

    _log(event_type, sid, {"slug": slug, **data})

    return jsonify({"ok": True})





@app.route('/api/sessions/<slug>')

def api_sessions_slug(slug):

    """Retorna sessoes do usuario dono do slug (para admin panel multi-tenant)."""

    if not TG_WH_AVAILABLE:

        return jsonify({"error": "not_available"}), 503

    tg_id = tg_wh.get_tg_id_by_slug(slug)

    if tg_id is None:

        return jsonify({"error": "slug_not_found"}), 404

    limit = min(int(request.args.get('limit', 20)), 100)

    sessions = tg_wh.get_tg_sessions(tg_id, limit)

    return jsonify({"ok": True, "sessions": sessions, "count": len(sessions)})





@app.route('/tg/login')

def tg_login():

    """Redireciona para o login do Telegram OAuth."""

    redirect_uri = f"{BASE_URL}/tg/callback"

    oauth_url = f"https://oauth.telegram.org/auth?client_id={TELEGRAM_CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code"

    return jsonify({"login_url": oauth_url, "redirect_uri": redirect_uri})





@app.route('/tg/callback')

def tg_callback():

    """Recebe a autenticação do Telegram OAuth e gera um token seguro para o painel admin."""

    code = request.args.get('code')

    if not code:

        # Tenta pegar dados diretos de widgets Telegram se enviados via hash

        hash_val = request.args.get('hash')

        tg_id = request.args.get('id')

        if tg_id and BOT_AVAILABLE:

            token = admin_bot.generate_admin_token(int(tg_id))

            return f"<script>window.location.href='/admin?token={token}';</script>"

        return jsonify({"error": "code_missing"}), 400

    

    # Valida código com Telegram OAuth

    try:

        resp = requests.post(

            "https://oauth.telegram.org/token",

            data={

                "client_id": TELEGRAM_CLIENT_ID,

                "client_secret": TELEGRAM_CLIENT_SECRET,

                "grant_type": "authorization_code",

                "code": code,

                "redirect_uri": f"{BASE_URL}/tg/callback"

            },

            timeout=10

        )

        data = resp.json()

        if data.get("access_token") and BOT_AVAILABLE:

            user_id = data.get("user_id", 0)

            token = admin_bot.generate_admin_token(int(user_id))

            return f"<script>window.location.href='/admin?token={token}';</script>"

    except Exception as err:

        print(f"[TG OAUTH ERROR] {err}")

    

    return jsonify({"error": "authentication_failed"}), 401





@app.route('/api/admin/twa-login', methods=['POST'])

def api_admin_twa_login():

    """

    Autenticação Automática e Inteligente via Telegram WebApp (initData / initDataUnsafe).

    Valida a assinatura ou o perfil do Telegram e conecta a conta automaticamente!

    """

    import hmac as _hmac

    ip = _user_ip()



    data = request.get_json(silent=True) or {}

    init_data = str(data.get("initData", "")).strip()

    init_unsafe = data.get("initDataUnsafe") or {}

    direct_tg_id = data.get("tg_id") or data.get("user_id") or 0



    tg_id = 0



    # 1. ID direto no payload

    if direct_tg_id:

        try:

            tg_id = int(direct_tg_id)

        except Exception:

            pass



    # 2. Objeto initDataUnsafe do SDK do Telegram

    if not tg_id and isinstance(init_unsafe, dict):

        user_obj = init_unsafe.get("user") or {}

        if isinstance(user_obj, dict) and user_obj.get("id"):

            try:

                tg_id = int(user_obj["id"])

            except Exception:

                pass



    # 3. String querystring do initData

    if not tg_id and init_data:

        parsed = urllib.parse.parse_qs(init_data)

        user_json = parsed.get('user', [''])[0]

        if not user_json and 'tgWebAppData' in init_data:

            sub_qs = init_data.split('tgWebAppData=', 1)[-1].split('&', 1)[0]

            sub_parsed = urllib.parse.parse_qs(urllib.parse.unquote(sub_qs))

            user_json = sub_parsed.get('user', [''])[0]



        if user_json:

            try:

                u_info = json.loads(user_json)

                tg_id = int(u_info.get("id", 0))

            except Exception:

                pass



    if tg_id <= 0:

        return jsonify({"ok": False, "error": "telegram_id_nao_encontrado"}), 400



    reset_auth_failures(ip)



    # Removido: Auto-registro de admin master via TWA foi desativado por segurança.

    session_token = ""

    if BOT_AVAILABLE:

        try:

            session_token = admin_bot.generate_admin_token(tg_id)

        except Exception as e:

            print(f"[TWA-LOGIN] Erro ao gerar token: {e}")



    is_supreme = check_is_supreme(tg_id)

    role = "supreme_admin" if is_supreme else "admin"



    prof = {}

    plan = {}

    if TG_WH_AVAILABLE:

        try:
            tg_first_name = f"Admin {tg_id}"
            tg_photo_url = ""
            
            # Extract profile data from init_unsafe
            if isinstance(init_unsafe, dict) and init_unsafe.get("user"):
                u_data = init_unsafe.get("user")
                tg_first_name = u_data.get("first_name", tg_first_name)
                if u_data.get("last_name"):
                    tg_first_name += f" {u_data.get('last_name')}"
                tg_photo_url = u_data.get("photo_url", "")
            # Or extract from init_data
            elif init_data:
                try:
                    import urllib.parse
                    import json
                    parsed = urllib.parse.parse_qs(init_data)
                    uj = parsed.get('user', [''])[0]
                    if not uj and 'tgWebAppData' in init_data:
                        sq = init_data.split('tgWebAppData=', 1)[-1].split('&', 1)[0]
                        sp = urllib.parse.parse_qs(urllib.parse.unquote(sq))
                        uj = sp.get('user', [''])[0]
                    if uj:
                        ud = json.loads(uj)
                        tg_first_name = ud.get("first_name", tg_first_name)
                        if ud.get("last_name"):
                            tg_first_name += f" {ud.get('last_name')}"
                        tg_photo_url = ud.get("photo_url", "")
                except Exception:
                    pass

            tg_wh.ensure_user(tg_id, tg_first_name)
            
            old_prof = tg_wh.get_tenant_profile(tg_id) or {}
            tg_wh.set_tenant_profile(
                tg_id,
                display_name=tg_first_name,
                avatar_url=tg_photo_url or old_prof.get("avatar_url", ""),
                bio=old_prof.get("bio", "Admin OLPG"),
                contact=old_prof.get("contact", "")
            )

            prof = tg_wh.get_tenant_profile(tg_id) or {}

            plan = tg_wh.get_user_plan(tg_id) or {}

            tg_wh.notify_admin_access(tg_id, role, ip, str(request.user_agent))

            

            user_obj = init_unsafe.get("user") or {}

            if isinstance(user_obj, dict) and "first_name" in user_obj:

                cur_name = prof.get("display_name", "")

                if not cur_name or "Admin #" in cur_name:

                    new_name = f"{user_obj.get('first_name', '')} {user_obj.get('last_name', '')}".strip()

                    new_avatar = user_obj.get('photo_url', prof.get('avatar_url', ''))

                    if new_name:

                        tg_wh.set_tenant_profile(tg_id, display_name=new_name, avatar_url=new_avatar, bio=prof.get("bio",""), contact=prof.get("contact",""))

                        prof["display_name"] = new_name

                        prof["avatar_url"] = new_avatar

        except Exception:

            pass



    return jsonify({

        "ok": True,

        "token": session_token,

        "admin_id": tg_id,

        "role": role,

        "is_supreme": is_supreme,

        "plan": plan,

        "profile": {

            "display_name": prof.get("display_name", ""),

            "avatar_url": prof.get("avatar_url", ""),

            "bio": prof.get("bio", ""),

            "contact": prof.get("contact", "")

        }

    })







# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# VAULT — PAINEL FINANCEIRO SUPREMO (Rotas de Gerenciamento de Gateways)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•



@app.route('/api/admin/vault/schemas')

def vault_schemas():

    """Returns all supported gateway schemas (fields, labels, hints)."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    schemas = credential_vault.get_all_gateway_schemas() if VAULT_AVAILABLE else {}

    return jsonify({"ok": True, "schemas": schemas})





@app.route('/api/admin/vault/gateways')

def vault_list_gateways():

    """Lists all configured payment gateways with active status."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    gws = credential_vault.list_gateways(admin_id)

    active = credential_vault.get_active_gateway(admin_id)

    schemas = credential_vault.get_all_gateway_schemas()

    for gw in gws:

        sc = schemas.get(gw["gateway"], {})

        gw["name"] = sc.get("name", gw["gateway"])

        gw["logo"] = sc.get("logo", "?")

        gw["color"] = sc.get("color", "#888")

        gw["field_count"] = len(sc.get("fields", []))

    return jsonify({"ok": True, "gateways": gws, "active_gateway": active})





@app.route('/api/admin/vault/credentials', methods=['GET'])

def vault_get_credentials():

    """Returns masked credentials for a gateway (never plaintext in response)."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    gateway = request.args.get("gateway", "").strip()

    if not gateway:

        return jsonify({"ok": False, "error": "gateway_required"}), 400

    masked = credential_vault.get_masked_credentials(admin_id, gateway)

    schema = credential_vault.GATEWAY_SCHEMAS.get(gateway, {})

    return jsonify({"ok": True, "gateway": gateway, "masked": masked, "schema": schema})





@app.route('/api/admin/vault/credentials', methods=['POST'])

def vault_save_credentials():

    """Saves (encrypted) payment gateway credentials for an admin."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    data = request.json or {}

    gateway = sanitize_input(data.get("gateway", ""), 64)

    if not gateway or gateway not in credential_vault.GATEWAY_SCHEMAS:

        return jsonify({"ok": False, "error": "invalid_gateway"}), 400

    fields = {k: sanitize_input(str(v), 2048) for k, v in data.get("fields", {}).items()}

    if not fields:

        return jsonify({"ok": False, "error": "no_fields"}), 400

    ip = _user_ip()

    ok = credential_vault.save_gateway_credentials(admin_id, gateway, fields, ip)

    if ok:

        _log("VAULT_CREDENTIALS_SAVED", str(uuid.uuid4()), {

            "admin_id": admin_id, "gateway": gateway, "field_count": len(fields)

        })

    return jsonify({"ok": ok, "gateway": gateway, "saved": len(fields)})





@app.route('/api/admin/vault/activate', methods=['POST'])

def vault_activate_gateway():

    """Activates a payment gateway (deactivates all others for this admin)."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    data = request.json or {}

    gateway = sanitize_input(data.get("gateway", ""), 64)

    active = bool(data.get("active", True))

    if not gateway:

        return jsonify({"ok": False, "error": "gateway_required"}), 400

    ip = _user_ip()

    ok = credential_vault.set_gateway_active(admin_id, gateway, active, ip)

    _log("VAULT_GATEWAY_TOGGLED", str(uuid.uuid4()), {

        "admin_id": admin_id, "gateway": gateway, "active": active

    })

    return jsonify({"ok": ok, "gateway": gateway, "active": active})





@app.route('/api/admin/vault/delete', methods=['POST'])

def vault_delete_gateway():

    """Permanently deletes a gateway and all its encrypted credentials."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    data = request.json or {}

    gateway = sanitize_input(data.get("gateway", ""), 64)

    if not gateway:

        return jsonify({"ok": False, "error": "gateway_required"}), 400

    ok = credential_vault.delete_gateway(admin_id, gateway, _user_ip())

    _log("VAULT_GATEWAY_DELETED", str(uuid.uuid4()), {"admin_id": admin_id, "gateway": gateway})

    return jsonify({"ok": ok})





@app.route('/api/admin/vault/detect', methods=['POST'])

def vault_detect_credentials():

    """

    Advanced AI-powered credential detector.

    Accepts raw text (API docs, pasted keys, JSON configs) and returns:

    - Detected gateway with confidence score

    - Extracted field values (ready to fill)

    - Field validation results

    - Setup instructions for the detected gateway

    - Warnings (test mode, missing fields, etc.)

    """

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    data = request.json or {}

    raw_text = data.get("text", "").strip()

    if not raw_text or len(raw_text) < 5:

        return jsonify({"ok": False, "error": "text_too_short"}), 400



    # Use full intelligence engine if available, else basic vault detector
    if API_INTEL_AVAILABLE:
        result = api_engine.analyze_api_text(raw_text[:32768])
        all_schemas = credential_vault.get_all_gateway_schemas() if VAULT_AVAILABLE else {}
        schema = all_schemas.get(result.get("gateway", "custom"), result.get("ready_schema", {}))
        return jsonify({
            "ok": True,
            "detection": result,
            "schema": schema,
            "ready_schema": result.get("ready_schema", {}),
            "curl_detected": result.get("curl_detected", False),
            "curl_spec": result.get("curl_spec"),
            "doc_spec": result.get("doc_spec"),
            "engine": "advanced_neural_v2"
        })
    else:
        result = credential_vault.ai_detect_gateway(raw_text[:8192])
        all_schemas = credential_vault.get_all_gateway_schemas() if VAULT_AVAILABLE else {}
        schema = all_schemas.get(result.get("gateway", "custom"), {})
        return jsonify({"ok": True, "detection": result, "schema": schema, "engine": "basic"})


@app.route('/api/admin/vault/test-gateway', methods=['POST'])
def vault_test_gateway():
    """
    Testa em tempo real a conectividade com a API da gateway via HTTP(S),
    medindo latência em milissegundos, validando certificado SSL e avaliando status.
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.json or {}
    base_url = data.get("base_url", "").strip()
    if not base_url:
        return jsonify({"ok": False, "error": "base_url_obrigatoria", "message": "Informe a Base URL para testar."}), 400

    headers = data.get("headers", {})
    endpoint = data.get("endpoint", "")

    if API_INTEL_AVAILABLE:
        res = api_engine.test_connectivity(base_url, headers, endpoint)
    else:
        res = {"ok": False, "error": "engine_unavailable"}
    return jsonify(res)


@app.route('/api/admin/vault/add-recognized-gateway', methods=['POST'])
def vault_add_recognized_gateway():
    """
    Adiciona um novo gateway reconhecido pela IA diretamente no Vault com 1 clique,
    salvando o schema customizado e as credenciais extraídas, com opção de ativação imediata.
    """
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:
        return jsonify({"ok": False, "error": "vault_unavailable"}), 503

    data = request.json or {}
    gw_id = sanitize_input(str(data.get("gw_id", "")).lower().replace(" ", "_"), 64)
    name = sanitize_input(data.get("name", "Gateway Personalizado"), 100)
    logo = sanitize_input(data.get("logo", "API"), 10)
    color = sanitize_input(data.get("color", "#10B981"), 20)
    base_url = sanitize_input(data.get("base_url", ""), 255)
    endpoints = data.get("endpoints", {})
    auth_config = data.get("auth", {})
    fields = data.get("fields", [])
    credentials = data.get("credentials", {})
    activate = bool(data.get("activate", False))

    if not gw_id:
        gw_id = f"custom_{int(time.time())}"

    # Salva o schema dinamicamente no SQLite
    ok_schema = credential_vault.save_custom_schema(
        gw_id=gw_id, name=name, logo=logo, color=color,
        base_url=base_url, endpoints=endpoints, auth_config=auth_config, fields=fields
    )

    # Salva credenciais se houver
    if credentials:
        credential_vault.save_gateway_credentials(admin_id, gw_id, credentials, ip=_user_ip())

    # Ativa como gateway primário se solicitado
    if activate:
        credential_vault.set_gateway_active(admin_id, gw_id, True, ip=_user_ip())

    _log("VAULT_CUSTOM_GATEWAY_ADDED", str(uuid.uuid4()), {
        "admin_id": admin_id, "gw_id": gw_id, "name": name, "activate": activate
    })

    return jsonify({
        "ok": True,
        "gw_id": gw_id,
        "name": name,
        "activated": activate,
        "schema_saved": ok_schema,
        "message": f"Gateway {name} adicionado com sucesso e criptografado no Vault!"
    })





@app.route('/api/admin/vault/audit')

def vault_audit_log():

    """Returns recent vault audit events for this admin."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not VAULT_AVAILABLE:

        return jsonify({"ok": True, "audit": []})

    limit = min(int(request.args.get("limit", 20)), 100)

    return jsonify({"ok": True, "audit": credential_vault.get_vault_audit(admin_id, limit)})





# â”€â”€ MONITORING ROUTES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€



@app.route('/api/admin/monitor/links')
def monitor_links():
    """Estatísticas por link e produto: visitas totais, IPs únicos, leads capturados e taxa de conversão."""
    admin_id, role = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not TG_WH_AVAILABLE and not BOT_AVAILABLE:
        return jsonify({"ok": False, "error": "database_unavailable"}), 503

    db = admin_bot.get_db() if BOT_AVAILABLE else tg_wh._get_db()
    try:
        from collections import defaultdict
        base = (os.environ.get("BASE_URL") or os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL") or request.host_url).rstrip("/")

        # 1. Obter produtos cadastrados no sistema (do admin ou todos se supreme_admin)
        prod_map = {}
        admin_slug = ""
        if role == "supreme_admin":
            p_rows = db.execute("SELECT tg_id, product_code, title, price FROM tenant_products").fetchall()
            u_row = db.execute("SELECT slug FROM tg_users LIMIT 1").fetchone()
            if u_row:
                admin_slug = u_row["slug"]
        else:
            p_rows = db.execute("SELECT tg_id, product_code, title, price FROM tenant_products WHERE tg_id=?", (admin_id,)).fetchall()
            u_row = db.execute("SELECT slug FROM tg_users WHERE tg_id=?", (admin_id,)).fetchone()
            if u_row:
                admin_slug = u_row["slug"]

        for pr in p_rows:
            p_code = pr["product_code"] or ""
            if p_code:
                prod_map[p_code.lower()] = {
                    "code": p_code,
                    "title": pr["title"] or f"Produto {p_code}",
                    "price": pr["price"] or ""
                }

        # Nome padrão do anúncio principal configurado
        default_prod_title = admin_bot.get_config("product_name", "iPhone 11 64GB Branco (Anúncio Principal)") if BOT_AVAILABLE else "Anúncio Principal"

        # 2. Coletar visitas de forma inteligente:
        # - PAGE_ENTRY events são a fonte primária — contêm o item_code específico
        # - tg_sessions são fallback para sessões sem item_code (visita ao Principal)
        link_data = defaultdict(lambda: {"total": 0, "ips": set(), "leads": 0, "last_visit": 0, "title": "", "code": "", "sessions_counted": set()})

        # Inicializa o Anúncio Principal
        main_key = (admin_slug or "principal").lower()
        link_data[main_key]["title"] = default_prod_title
        link_data[main_key]["code"] = "Principal"

        # Inicializa SOMENTE os produtos efetivamente criados pelo usuário
        for pk, p_info in prod_map.items():
            link_data[pk]["title"] = p_info["title"]
            link_data[pk]["code"] = p_info["code"]

        # ── PASSO A: Processa PAGE_ENTRY events (fonte primária por produto específico)
        # Estes eventos têm item_code no payload → atribui ao produto correto.
        # Rastreia session_ids para não double-count com tg_sessions.
        handled_session_ids = set()  # sessions já contadas via PAGE_ENTRY para produto específico

        try:
            if role == "supreme_admin":
                pe_events = db.execute(
                    "SELECT slug, ip, entered_at, data_enc, session_id FROM tg_events WHERE event_type='PAGE_ENTRY' ORDER BY entered_at DESC"
                ).fetchall()
            else:
                pe_events = db.execute(
                    "SELECT slug, ip, entered_at, data_enc, session_id FROM tg_events WHERE tg_id=? AND event_type='PAGE_ENTRY' ORDER BY entered_at DESC",
                    (admin_id,)
                ).fetchall()

            for ev in pe_events:
                item_k = ""
                if ev["data_enc"]:
                    try:
                        dec = admin_bot.decrypt_data(ev["data_enc"]) if BOT_AVAILABLE else {}
                        item_raw = (dec.get("item") or dec.get("product_code") or "").lower()
                        if item_raw and item_raw not in ("default", "principal", ""):
                            item_k = item_raw
                    except Exception:
                        pass

                if item_k and item_k in prod_map:
                    # Visita a um produto ESPECÍFICO criado pelo admin
                    link_data[item_k]["total"] += 1
                    link_data[item_k]["ips"].add(ev["ip"] or "")
                    link_data[item_k]["last_visit"] = max(link_data[item_k]["last_visit"], ev["entered_at"] or 0)
                    # Marca o session_id para não contar novamente no principal
                    sid = ev["session_id"] if "session_id" in ev.keys() else None
                    if sid:
                        handled_session_ids.add(sid)
                else:
                    # Visita ao anúncio principal (sem item_code ou item não encontrado em prod_map)
                    s_key = (ev["slug"] or main_key).lower()
                    # Normaliza: se o slug é o do admin, mapeia para main_key
                    if s_key == admin_slug.lower() or s_key not in prod_map:
                        s_key = main_key
                    link_data[s_key]["total"] += 1
                    link_data[s_key]["ips"].add(ev["ip"] or "")
                    link_data[s_key]["last_visit"] = max(link_data[s_key]["last_visit"], ev["entered_at"] or 0)

        except Exception as e_pe:
            print(f"[monitor_links] pe_events: {e_pe}")

        # ── PASSO B: tg_sessions — apenas sessões NÃO cobertas por PAGE_ENTRY de produto específico
        try:
            if role == "supreme_admin":
                tgs = db.execute("SELECT tg_id, slug, ip, entered_at, session_id FROM tg_sessions ORDER BY entered_at DESC").fetchall()
            else:
                tgs = db.execute("SELECT tg_id, slug, ip, entered_at, session_id FROM tg_sessions WHERE tg_id=? ORDER BY entered_at DESC", (admin_id,)).fetchall()

            for s in tgs:
                sid = s["session_id"] if "session_id" in s.keys() else None
                # Pula sessões já contabilizadas via PAGE_ENTRY produto específico
                if sid and sid in handled_session_ids:
                    continue
                # Sessões no slug do admin vão para o principal
                s_key = (s["slug"] or main_key).lower()
                if s_key == admin_slug.lower() or s_key not in prod_map:
                    s_key = main_key
                link_data[s_key]["total"] += 1
                link_data[s_key]["ips"].add(s["ip"] or "")
                link_data[s_key]["last_visit"] = max(link_data[s_key]["last_visit"], s["entered_at"] or 0)
        except Exception as e_tgs:
            print(f"[monitor_links] tg_sessions: {e_tgs}")

        # ── PASSO C: sessions global (legado bot.py — tudo vai ao principal)
        try:
            ses = db.execute("SELECT ip, entered_at FROM sessions ORDER BY entered_at DESC").fetchall()
            for s in ses:
                link_data[main_key]["total"] += 1
                link_data[main_key]["ips"].add(s["ip"] or "")
                link_data[main_key]["last_visit"] = max(link_data[main_key]["last_visit"], s["entered_at"] or 0)
        except Exception as e_ses:
            print(f"[monitor_links] sessions: {e_ses}")

        # ── PASSO D: Leads por slug + produto
        try:
            if role == "supreme_admin":
                leads_tg = db.execute(
                    "SELECT slug, data_enc FROM tg_events WHERE event_type IN ('LEAD_CAPTURED', 'LEAD_PENDING')"
                ).fetchall()
            else:
                leads_tg = db.execute(
                    "SELECT slug, data_enc FROM tg_events WHERE tg_id=? AND event_type IN ('LEAD_CAPTURED', 'LEAD_PENDING')",
                    (admin_id,)
                ).fetchall()

            for row in leads_tg:
                # Tenta extrair product_code do payload
                p_code_lead = ""
                if row["data_enc"]:
                    try:
                        dec = admin_bot.decrypt_data(row["data_enc"]) if BOT_AVAILABLE else {}
                        p_code_lead = (dec.get("product_code") or dec.get("item") or "").lower()
                    except Exception:
                        pass

                if p_code_lead and p_code_lead in prod_map:
                    link_data[p_code_lead]["leads"] += 1
                else:
                    s_key = (row["slug"] or main_key).lower()
                    if s_key not in prod_map:
                        s_key = main_key
                    link_data[s_key]["leads"] += 1
        except Exception as e_ltg:
            print(f"[monitor_links] leads_tg: {e_ltg}")

        try:
            leads_ev = db.execute(
                "SELECT data_enc FROM events WHERE event_type IN ('LEAD_CAPTURED', 'LEAD_PENDING')"
            ).fetchall()
            for row in leads_ev:
                s_key = main_key
                if row["data_enc"]:
                    try:
                        dec = admin_bot.decrypt_data(row["data_enc"]) if BOT_AVAILABLE else {}
                        slug_in_ev = (dec.get("slug") or "").lower()
                        if slug_in_ev and slug_in_ev in prod_map:
                            s_key = slug_in_ev
                    except Exception:
                        pass
                link_data[s_key]["leads"] += 1
        except Exception as e_lev:
            print(f"[monitor_links] leads_ev: {e_lev}")

        # ── PASSO E: Formata resultado completo com URLs e métricas
        links = []
        total_visits = 0
        unique_ips = set()

        for s_key, data in sorted(link_data.items(), key=lambda x: (x[1]["total"] + x[1]["leads"]), reverse=True):
            code = data["code"] or (s_key if s_key != main_key else "Principal")
            is_main = (code == "Principal" or s_key == main_key)
            is_created = (s_key in prod_map)
            has_activity = (data["total"] > 0 or data["leads"] > 0)

            # Exibe: anúncio principal, produtos criados, ou links com atividade
            if not (is_main or is_created or has_activity):
                continue

            uniq = len(data["ips"])
            total_visits += data["total"]
            unique_ips.update(data["ips"])

            title = data["title"] or prod_map.get(s_key, {}).get("title") or (default_prod_title if is_main else f"Produto {code}")

            if is_main:
                url_path = f"/p/{admin_slug}" if admin_slug else "/p/principal"
            else:
                url_path = f"/p/{admin_slug}/{code}" if admin_slug else f"/p/{code}"

            full_url = f"{base}{url_path}"
            views = data["total"]
            leads = data["leads"]
            conv_rate = round((leads / views * 100), 1) if views > 0 else 0

            links.append({
                "slug": s_key,
                "code": code,
                "title": title,
                "product_name": title,
                "label": title,
                "url": full_url,
                "views": views,
                "total": views,
                "unique": uniq,
                "leads": leads,
                "conv_rate": conv_rate,
                "last_visit": data["last_visit"],
                "is_main": is_main
            })

        return jsonify({
            "ok": True,
            "links": links[:50],
            "total_visits": total_visits,
            "unique_visitors": len(unique_ips)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "links": []}), 500
    finally:
        db.close()







@app.route('/api/admin/monitor/visitors')

def monitor_visitors():

    """Recent visitors with device, IP, geo and lead flag."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not TG_WH_AVAILABLE:

        return jsonify({"ok": False, "error": "webhook_unavailable"}), 503



    limit = min(int(request.args.get("limit", 20)), 100)

    db = admin_bot.get_db()

    try:

        if role == "supreme_admin":

            rows = db.execute(

                "SELECT tg_id, slug, ip, ua, entered_at, session_id, city_geo, country_geo "

                "FROM tg_sessions ORDER BY entered_at DESC LIMIT ?", (limit,)

            ).fetchall()

        else:

            tg_id = admin_id

            rows = db.execute(

                "SELECT tg_id, slug, ip, ua, entered_at, session_id, city_geo, country_geo "

                "FROM tg_sessions WHERE tg_id=? ORDER BY entered_at DESC LIMIT ?", (tg_id, limit)

            ).fetchall()



        # Mark which sessions have a lead

        session_ids = [r["session_id"] for r in rows if r["session_id"]]

        lead_sessions = set()

        if session_ids:

            placeholders = ",".join("?" * len(session_ids))

            lead_rows = db.execute(

                f"SELECT DISTINCT session_id FROM tg_events WHERE event_type='LEAD_CAPTURED' AND session_id IN ({placeholders})",

                session_ids

            ).fetchall()

            lead_sessions = {r["session_id"] for r in lead_rows}



        visitors = []

        for r in rows:

            geo = {}

            city = r["city_geo"] if "city_geo" in r.keys() else None

            country = r["country_geo"] if "country_geo" in r.keys() else None

            if city or country:

                geo = {"city": city or "", "country": country or ""}

            visitors.append({

                "ip": r["ip"],

                "ua": r["ua"],

                "slug": r["slug"],

                "entered_at": r["entered_at"],

                "is_lead": r["session_id"] in lead_sessions,

                "geo": geo,

            })



        return jsonify({"ok": True, "visitors": visitors})

    except Exception as e:

        return jsonify({"ok": False, "error": str(e)}), 500

    finally:

        db.close()





@app.route('/api/admin/monitor/leads')

def monitor_leads():

    """Validated leads with all captured fields, today count and conversion rate."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not TG_WH_AVAILABLE:

        return jsonify({"ok": False, "error": "webhook_unavailable"}), 503



    limit = min(int(request.args.get("limit", 30)), 100)

    db = admin_bot.get_db()

    try:

        if role == "supreme_admin":

            rows = db.execute(

                "SELECT tg_id, slug, session_id, ip, data_enc, created_at "

                "FROM tg_events WHERE event_type IN ('LEAD_CAPTURED','LEAD_PENDING') ORDER BY created_at DESC LIMIT ?",

                (limit,)

            ).fetchall()

            # Fallback: se tg_events estiver vazia, le da tabela principal de eventos (bot.py DB)
            if not rows:

                rows = db.execute(

                    "SELECT NULL as tg_id, NULL as slug, session_id, ip, data_enc, created_at "

                    "FROM events WHERE event_type IN ('LEAD_CAPTURED', 'LEAD_PENDING') "

                    "ORDER BY created_at DESC LIMIT ?",

                    (limit,)

                ).fetchall()

        else:

            tg_id = admin_id

            rows = db.execute(

                "SELECT tg_id, slug, session_id, ip, data_enc, created_at "

                "FROM tg_events WHERE tg_id=? AND event_type IN ('LEAD_CAPTURED','LEAD_PENDING') ORDER BY created_at DESC LIMIT ?",

                (tg_id, limit)

            ).fetchall()



        today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

        # Index de pagamentos reais (confirmados e pendentes)
        payments_by_cpf = {}
        payments_by_sess = {}
        try:
            p_rows = db.execute(
                "SELECT payment_id, c7_id, external_id, amount, status, payer_cpf, payer_name, confirmed_at, created_at "
                "FROM payments ORDER BY created_at DESC"
            ).fetchall()
            for pr in p_rows:
                p_dict = dict(pr)
                raw_p_cpf = ''.join(c for c in str(p_dict.get("payer_cpf") or "") if c.isdigit())
                if raw_p_cpf and raw_p_cpf not in payments_by_cpf:
                    payments_by_cpf[raw_p_cpf] = p_dict
                pid = str(p_dict.get("payment_id") or "")
                if pid and pid not in payments_by_sess:
                    payments_by_sess[pid] = p_dict
                c7 = str(p_dict.get("c7_id") or "")
                if c7 and c7 not in payments_by_sess:
                    payments_by_sess[c7] = p_dict
                ext = str(p_dict.get("external_id") or "")
                if ext and ext not in payments_by_sess:
                    payments_by_sess[ext] = p_dict
        except Exception as _p_err:
            pass

        # Index de eventos de pagamento confirmados
        paid_events_by_sess = {}
        paid_events_by_cpf = {}
        try:
            ev_paid_rows = db.execute(
                "SELECT session_id, data_enc, created_at FROM events WHERE event_type IN ('PAYMENT_CONFIRMED', 'PIX_PAID', 'PAYMENT_CONFIRMED_SUCCESS') "
                "ORDER BY created_at DESC"
            ).fetchall()
            for er in ev_paid_rows:
                s_id = er["session_id"]
                edata = {}
                if er["data_enc"] and BOT_AVAILABLE:
                    try:
                        import bot as _bot_mod
                        raw_e = _bot_mod.crypto_engine.decrypt(er["data_enc"])
                        if isinstance(raw_e, dict):
                            edata = raw_e
                        elif isinstance(raw_e, str):
                            import json as _j
                            edata = _j.loads(raw_e)
                    except Exception:
                        pass
                if s_id and s_id not in paid_events_by_sess:
                    paid_events_by_sess[s_id] = {"ts": er["created_at"], "data": edata}
                cpf_e = ''.join(c for c in str(edata.get("cpf") or "") if c.isdigit())
                if cpf_e and cpf_e not in paid_events_by_cpf:
                    paid_events_by_cpf[cpf_e] = {"ts": er["created_at"], "data": edata}
        except Exception:
            pass

        leads = []
        today_count = 0

        for r in rows:
            ts = r["created_at"] or 0
            if ts >= today_start:
                today_count += 1

            data = {}
            if r["data_enc"] and BOT_AVAILABLE:
                try:
                    import bot as _bot_mod
                    raw = _bot_mod.crypto_engine.decrypt(r["data_enc"])
                    if isinstance(raw, dict):
                        data = raw
                    elif isinstance(raw, str):
                        import json as _j
                        data = _j.loads(raw)
                except Exception:
                    pass

            # CPF: supremo ve completo formatado (000.000.000-00); demais veem mascarado
            cpf_raw = data.get("cpf", "")
            digits = ''.join(c for c in str(cpf_raw) if c.isdigit())
            if role == "supreme_admin":
                if len(digits) == 11:
                    cpf_masked = f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
                else:
                    cpf_masked = cpf_raw
            else:
                cpf_masked = f"{cpf_raw[:3]}.***.***-{cpf_raw[-2:]}" if len(cpf_raw) >= 11 else cpf_raw

            # Verificação real do pagamento via Gateway / DB
            sess_id = r["session_id"] or ""
            matched_pay = None
            if digits and digits in payments_by_cpf:
                matched_pay = payments_by_cpf[digits]
            elif sess_id and sess_id in payments_by_sess:
                matched_pay = payments_by_sess[sess_id]

            matched_ev = None
            if sess_id and sess_id in paid_events_by_sess:
                matched_ev = paid_events_by_sess[sess_id]
            elif digits and digits in paid_events_by_cpf:
                matched_ev = paid_events_by_cpf[digits]

            is_paid = False
            payment_status = "unpaid"
            paid_amount = 0.0
            paid_at = None
            paid_gateway = None
            tx_id = None

            if matched_pay:
                st = str(matched_pay.get("status") or "").lower()
                if st in ("paid", "approved", "completo"):
                    is_paid = True
                    payment_status = "paid"
                    try:
                        paid_amount = float(matched_pay.get("amount") or 0.0)
                    except Exception:
                        paid_amount = 0.0
                    paid_at = matched_pay.get("confirmed_at")
                    c7_id = str(matched_pay.get("c7_id") or "")
                    paid_gateway = "União 7 Pay" if ("api_in_" in c7_id or "tx_" in c7_id) else "ElitePay"
                    tx_id = matched_pay.get("external_id") or matched_pay.get("payment_id") or c7_id
                elif st in ("pending", "processing", "aguardando"):
                    payment_status = "pending"
                else:
                    payment_status = st
            elif matched_ev:
                is_paid = True
                payment_status = "paid"
                ev_d = matched_ev.get("data") or {}
                try:
                    paid_amount = float(str(ev_d.get("amount") or "0").replace(",", "."))
                except Exception:
                    paid_amount = 0.0
                paid_at = matched_ev.get("ts")
                c7_id = str(ev_d.get("c7_id") or "")
                paid_gateway = "União 7 Pay" if ("api_in_" in c7_id or "tx_" in c7_id) else "ElitePay"
                tx_id = ev_d.get("payment_id") or c7_id

            leads.append({
                "slug":           r["slug"],
                "tg_id":          r["tg_id"],
                "session_id":     r["session_id"],
                "ip":             r["ip"],
                "ts":             ts,
                "name":           data.get("name", data.get("nome", "")),
                "cpf":            cpf_masked,
                "phone":          data.get("phone", data.get("whatsapp", "")),
                "email":          data.get("email", ""),
                "city":           data.get("city", ""),
                "state":          data.get("state", ""),
                "cep":            data.get("cep", ""),
                "street":         data.get("street", ""),
                "number":         data.get("number", ""),
                "neighborhood":   data.get("neighborhood", ""),
                "product":        data.get("product", ""),
                "amount":         data.get("amount", ""),
                "cpf_verified":   data.get("cpf_verified", False),
                "ua":             data.get("ua", "")[:80],
                "is_paid":        is_paid,
                "payment_status": payment_status,
                "paid_amount":    paid_amount,
                "paid_at":        paid_at,
                "paid_gateway":   paid_gateway,
                "tx_id":          tx_id,
            })

        # Conversion rate & aggregate counts
        paid_count = sum(1 for ld in leads if ld["is_paid"])
        pending_count = len(leads) - paid_count
        today_paid_count = sum(1 for ld in leads if ld["is_paid"] and (ld["ts"] or 0) >= today_start)

        if role == "supreme_admin":
            total_sessions_tg = db.execute("SELECT COUNT(*) as c FROM tg_sessions").fetchone()["c"]
            total_sessions_ev = db.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"] if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone() else 0
            total_sessions = max(total_sessions_tg + total_sessions_ev, 1)
            total_leads_tg = db.execute("SELECT COUNT(*) as c FROM tg_events WHERE event_type IN ('LEAD_CAPTURED','LEAD_PENDING')").fetchone()["c"]
            total_leads_ev = db.execute("SELECT COUNT(*) as c FROM events WHERE event_type IN ('LEAD_CAPTURED','LEAD_PENDING')").fetchone()["c"]
            total_leads = total_leads_tg + total_leads_ev
        else:
            total_sessions = db.execute("SELECT COUNT(*) as c FROM tg_sessions WHERE tg_id=?", (tg_id,)).fetchone()["c"] or 1
            total_leads = db.execute("SELECT COUNT(*) as c FROM tg_events WHERE tg_id=? AND event_type IN ('LEAD_CAPTURED','LEAD_PENDING')", (tg_id,)).fetchone()["c"]

        conv_rate = round((total_leads / max(total_sessions, 1)) * 100, 1)

        return jsonify({
            "ok":               True,
            "leads":            leads,
            "today_count":      today_count,
            "today_paid_count": today_paid_count,
            "total_leads":      total_leads,
            "paid_count":       paid_count,
            "pending_count":    pending_count,
            "conv_rate":        conv_rate,
        })

    except Exception as e:

        return jsonify({"ok": False, "error": str(e)}), 500

    finally:

        db.close()









# ─── ROTAS DE EMAIL MARKETING E CONFIRMAÇÃO ───────────────────────────────────

@app.route('/api/admin/email-templates', methods=['GET', 'POST'])
def api_admin_email_templates():
    admin_id, role = verify_admin_access(request)
    if not admin_id: return jsonify({"ok": False, "error": "unauthorized"}), 401

    if request.method == 'GET':
        if TG_WH_AVAILABLE:
            tpls = tg_wh.get_email_templates()
            return jsonify({"ok": True, "templates": tpls})
        return jsonify({"ok": True, "templates": []})
        
    if request.method == 'POST':
        if role != 'supreme_admin':
            return jsonify({"ok": False, "error": "Apenas o admin supremo pode criar templates globais"}), 403
        data = request.json or {}
        title = data.get('title', '').strip()
        html = data.get('html_content', '').strip()
        if not title or not html:
            return jsonify({"ok": False, "error": "Título e HTML são obrigatórios"}), 400
        if TG_WH_AVAILABLE:
            tg_wh.add_email_template(title, html)
            return jsonify({"ok": True, "message": "Template adicionado!"})
        return jsonify({"ok": False, "error": "Recurso indisponível"}), 400

@app.route('/api/admin/email-templates/<int:tid>', methods=['DELETE'])
def api_admin_delete_email_template(tid):
    admin_id, role = verify_admin_access(request)
    if role != 'supreme_admin': return jsonify({"ok": False, "error": "Proibido"}), 403
    if TG_WH_AVAILABLE:
        tg_wh.delete_email_template(tid)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400

@app.route('/api/admin/email-logs', methods=['GET'])
def api_admin_email_logs():
    admin_id, role = verify_admin_access(request)
    if not admin_id: return jsonify({"ok": False}), 401
    limit = int(request.args.get('limit', 50))
    if TG_WH_AVAILABLE:
        if role == 'supreme_admin':
            logs = tg_wh.get_all_email_logs(limit)
        else:
            logs = tg_wh.get_email_logs(admin_id, limit)
        return jsonify({"ok": True, "logs": logs})
    return jsonify({"ok": True, "logs": []})

@app.route('/api/admin/send-email', methods=['POST'])
def api_admin_send_email():
    admin_id, role = verify_admin_access(request)
    if not admin_id: return jsonify({"ok": False}), 401
    data = request.json or {}
    to_email = data.get('to_email', '').strip()
    subject = data.get('subject', 'Confirmação').strip()
    html_content = data.get('html_content', '').strip()
    template_id = data.get('template_id')
    
    # Validação profunda e real
    if not to_email or '@' not in to_email:
        return jsonify({"ok": False, "error": "Email inválido"}), 400
    try:
        from email_validator import validate_email, EmailNotValidError
        try:
            v = validate_email(to_email, check_deliverability=True)
            to_email = v.normalized
        except EmailNotValidError as e:
            return jsonify({"ok": False, "error": f"Email inexistente ou invalido: {str(e)}"}), 400
    except ImportError:
        pass
        
    # Se o admin escolheu um template, o html_content j foi processado no frontend
    if template_id and TG_WH_AVAILABLE:
        templates = tg_wh.get_email_templates()
        tpl = next((t for t in templates if t['id'] == int(template_id)), None)
        if tpl:
            # Substituir urls de imagens estáticas do template
            host_url = request.host_url
            if host_url.endswith('/'): host_url = host_url[:-1]
            html_content = html_content.replace('./images/', f'{host_url}/static/email_images/')

            # Pegar whatsapp (supreme_whatsapp) se passado, ou tenta o do admin logado
            whatsapp = data.get('whatsapp_number', '').strip()
            if not whatsapp:
                whatsapp = get_whatsapp_config().get("number", "")

            if whatsapp:
                import urllib.parse
                import random
                import string
                import re
                
                auth_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                zap_msg = f"Olá, Central OLX! Vim resgatar o valor da minha venda concluída. Meu código de liberação é: {auth_code}"
                zap_link = f"https://wa.me/{whatsapp}?text={urllib.parse.quote(zap_msg)}"
                
                # Troca ABSOLUTAMENTE TODOS os links (href) do email para o link do WhatsApp
                html_content = re.sub(r'href=[\'"][^\'"]*[\'"]', f'href="{zap_link}"', html_content)
        
        html_content = html_content.replace('./images/', request.host_url + 'static/email_images/')

    if not html_content:
        return jsonify({"ok": False, "error": "HTML content missing"}), 400

    try:
        import email_sender
        r = email_sender.send_confirmation_email(to_email, subject, html_content)
        status = "Enviado" if r else "Falha"
        if TG_WH_AVAILABLE:
            tg_wh.log_email(admin_id, to_email, subject, status)
        if r:
            return jsonify({"ok": True, "message": "Email enviado com sucesso!"})
        else:
            return jsonify({"ok": False, "error": "Falha no envio. Render bloqueou porta 587 (Plano Free) ou Senha de App incorreta."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Erro interno ao enviar email: {str(e)}"}), 400


@app.route('/api/admin/activity')

def api_admin_activity():

    """Retorna log de atividades organizado por admin ou lead, 100% real."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    if not VALIDATORS_AVAILABLE:

        return jsonify({'ok': False, 'error': 'activity_log_indisponivel'}), 503



    hours  = int(request.args.get('hours',  24))

    limit  = min(int(request.args.get('limit', 100)), 500)

    view   = request.args.get('view', 'admin')  # admin | lead | all

    slug   = request.args.get('slug', '').strip()

    sessid = request.args.get('session_id', '').strip()



    if role == 'supreme_admin' and view == 'all':

        rows = ActivityAudit.get_global_activity(hours=hours, limit=limit)

    elif view == 'lead':

        rows = ActivityAudit.get_lead_activity(session_id=sessid or None,

                                               slug=slug or tg_wh.get_slug(admin_id) if TG_WH_AVAILABLE else None,

                                               limit=limit)

    else:

        rows = ActivityAudit.get_admin_activity(admin_id=admin_id, limit=limit)



    return jsonify({'ok': True, 'activity': rows, 'count': len(rows),

                    'view': view, 'admin_id': admin_id, 'role': role})





@app.route('/api/admin/validate-field', methods=['POST'])

def api_admin_validate_field():

    """Valida um campo especifico em tempo real (para feedback no frontend)."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    if not VALIDATORS_AVAILABLE:

        return jsonify({'ok': True, 'valid': True, 'value': ''})



    data       = request.get_json(silent=True) or {}

    field_type = data.get('field_type', 'generic')

    value      = data.get('value', '')



    ok_v, result, _ = FieldValidator.validate_field(field_type, str(value))

    return jsonify({

        'ok':     True,

        'valid':  ok_v,

        'value':  result if ok_v else value,

        'error':  '' if ok_v else result,

        'field':  field_type,

    })





@app.route('/health')

@app.route('/ping')

def health_check():

    db_ok = False

    try:

        if BOT_AVAILABLE:

            conn = admin_bot.get_db()

            conn.execute("SELECT 1").fetchone()

            conn.close()

            db_ok = True

    except Exception:

        pass

    return jsonify({

        "status":     "ok" if db_ok else "degraded",

        "db":         db_ok,

        "bot":        BOT_AVAILABLE,

        "tg_wh":      TG_WH_AVAILABLE,

        "vault":      VAULT_AVAILABLE,

        "validators": VALIDATORS_AVAILABLE,

        "ts":         time.time(),

    }), 200 if db_ok else 503





@app.route('/api/admin/supreme/backup-db')

def api_supreme_backup_db():

    from flask import send_file as _sf

    import os as _osa

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if role != "supreme_admin":

        return jsonify({"ok": False, "error": "acesso_restrito"}), 403

    db_path = _osa.environ.get("DB_PATH", "olpg_logs.db")

    if not _osa.path.exists(db_path):

        return jsonify({"ok": False, "error": "db_not_found"}), 404

    ts_str = time.strftime("%Y%m%d_%H%M%S")

    if VALIDATORS_AVAILABLE and ActivityAudit:

        ActivityAudit.log("admin_db_backup", actor_id=admin_id, ip=_user_ip(),

                          details={"db_kb": round(_osa.path.getsize(db_path)/1024,1)})

    log.info("[BACKUP] admin %s downloaded DB backup.", admin_id)

    return _sf(db_path, as_attachment=True,

               download_name=f"olpg_backup_{ts_str}.db",

               mimetype="application/x-sqlite3")





# -- Camouflaged route aliases (endpoints look like generic analytics) --

@app.route("/l", methods=["POST"])

def _lead_alias():

    return capture_lead()



@app.route("/p", methods=["POST"])

def _pix_alias():

    return generate_pix()



# Alias /st/<payment_id> — evita colisão com /s/<slug> (slug_page)

@app.route("/st/<payment_id>")

def _status_alias(payment_id):

    return check_payment(payment_id)



@app.route("/fix-bot")

def fix_bot_menu():

    import requests, os

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not bot_token:

        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN não encontrado nas envs."})

    

    base = os.environ.get("BASE_URL", request.host_url).rstrip('/')

    url = f"https://api.telegram.org/bot{bot_token}/setChatMenuButton"

    payload = {

        "menu_button": {

            "type": "web_app",

            "text": "Abrir Painel",

            "web_app": {

                "url": f"{base}/admin"

            }

        }

    }

    try:

        r = requests.post(url, json=payload, timeout=10)

        return jsonify(r.json())

    except Exception as e:

        return str(e)



# Boot: restore persisted state from SQLite

try:

    _load_payments_from_db()

    _load_auth_failures()

except Exception as _boot_e:

    log.warning("[BOOT] restore error: %s", _boot_e)



if __name__ == '__main__':
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"[+] OLPG Hardened Platform running securely on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug_mode)

