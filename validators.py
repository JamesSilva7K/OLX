# -*- coding: utf-8 -*-
"""
OLPG -- Advanced Validation Engine & Activity Audit System
==========================================================
Motor de validacao avancada de campos e auditoria de movimentacoes.
"""
import re, time, json, unicodedata, logging
logger = logging.getLogger("OLPG_VALIDATOR")

_INJECTION_PATTERNS = re.compile(
    r"(<script|javascript:|on\w+\s*=|data:\s*text|vbscript:|"
    r"union\s+select|drop\s+table|insert\s+into|exec\s*\(|"
    r"\beval\s*\(|\balert\s*\(|document\.cookie|window\.location|"
    r"base64_decode|cmd\.exe|/etc/passwd)",
    re.IGNORECASE
)
_BLOCKED_WORDS = {"script","javascript","eval","alert","onclick","onerror","onload","iframe"}

_ALLOWED = {
    "name":         re.compile(r"^[A-Za-z\u00C0-\u024F\s'\-\.]{2,120}$"),
    "phone":        re.compile(r"^\+?[\d\s\(\)\-]{8,20}$"),
    "cpf":          re.compile(r"^\d{11}$"),
    "cep":          re.compile(r"^\d{8}$"),
    "email":        re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,10}$"),
    "price":        re.compile(r"^\d{1,8}([.,]\d{1,2})?$"),
    "url":          re.compile(r"^https?://[^\s<>\"]{5,500}$"),
    "slug":         re.compile(r"^[a-z0-9_\-]{2,60}$"),
    "product_name": re.compile(r"^[\w\s\.\-\+\/\(\)&%!,]{2,200}$"),
    "wa_number":    re.compile(r"^55\d{10,11}$"),
    "channel_id":   re.compile(r"^-?\d{6,15}$"),
    "otp":          re.compile(r"^\d{6}$"),
}
_MAX_LEN = {
    "name":120,"phone":25,"cpf":14,"cep":9,"email":100,"price":20,
    "url":500,"slug":60,"product_name":200,"description":5000,
    "wa_number":15,"channel_id":20,"tg_id":15,"otp":6,"generic":500,
}

VALID_DDDS = {11,12,13,14,15,16,17,18,19,21,22,24,27,28,31,32,33,34,35,37,38,
              41,42,43,44,45,46,47,48,49,51,53,54,55,61,62,63,64,65,66,67,68,
              69,71,73,74,75,77,79,81,82,83,84,85,86,87,88,89,91,92,93,94,95,96,97,98,99}

class FieldValidator:
    @staticmethod
    def sanitize(value, max_len=500, field_type="generic"):
        if not isinstance(value, str): return ""
        value = unicodedata.normalize("NFKC", value).strip()
        value = re.sub(r"<[^>]{0,200}>", "", value)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
        return value[:_MAX_LEN.get(field_type, max_len)]

    @staticmethod
    def has_injection(value):
        if not value: return False
        if _INJECTION_PATTERNS.search(value): return True
        lower = value.lower()
        return any(w in lower for w in _BLOCKED_WORDS)

    @classmethod
    def validate_name(cls, value):
        v = cls.sanitize(value, field_type="name")
        if cls.has_injection(v): return False, "Nome contem caracteres nao permitidos."
        if not v or len(v) < 3: return False, "Nome muito curto (minimo 3 caracteres)."
        if not re.match(r"^[A-Za-z\u00C0-\u024F\s'\-\.]{2,120}$", v):
            return False, "Nome contem caracteres invalidos."
        parts = [p for p in v.split() if len(p) >= 2]
        if len(parts) < 2: return False, "Informe o nome completo (Nome e Sobrenome)."
        return True, v

    @classmethod
    def validate_phone(cls, value):
        v = re.sub(r"[\s\-\(\)\+]", "", cls.sanitize(value, field_type="phone"))
        if not v.isdigit(): return False, "Telefone deve conter apenas numeros."
        digits = v[2:] if v.startswith("55") else v
        if len(digits) < 10 or len(digits) > 11:
            return False, "Numero de telefone invalido. Use DDD + numero (ex: 11999999999)."
        ddd = int(digits[:2])
        if ddd not in VALID_DDDS:
            return False, f"DDD {ddd} invalido. Verifique seu numero."
        number_part = digits[2:]
        if len(number_part) == 9 and number_part[0] != "9":
            return False, "Celular com 9 digitos deve comecar com 9."
        return True, f"+55{digits}"

    @classmethod
    def validate_cpf(cls, value):
        d = re.sub(r"\D", "", cls.sanitize(value, field_type="cpf"))
        if len(d) != 11: return False, "CPF deve ter 11 digitos."
        if len(set(d)) == 1: return False, "CPF invalido (sequencia repetida)."
        ns = [int(c) for c in d]
        s1 = sum(ns[i] * (10 - i) for i in range(9))
        r1 = 11 - (s1 % 11); dv1 = 0 if r1 >= 10 else r1
        if ns[9] != dv1: return False, "CPF matematicamente invalido."
        s2 = sum(ns[i] * (11 - i) for i in range(10))
        r2 = 11 - (s2 % 11); dv2 = 0 if r2 >= 10 else r2
        if ns[10] != dv2: return False, "CPF matematicamente invalido."
        return True, f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"

    @classmethod
    def validate_cep(cls, value):
        v = re.sub(r"\D", "", cls.sanitize(value, field_type="cep"))
        if len(v) != 8 or not v.isdigit(): return False, "CEP deve ter 8 digitos."
        if v in ("00000000","99999999","11111111"): return False, "CEP invalido."
        return True, f"{v[:5]}-{v[5:]}"

    @classmethod
    def validate_price(cls, value):
        v = cls.sanitize(value, field_type="price").replace(",", ".")
        if not re.match(r"^\d{1,8}([.]\d{1,2})?$", v):
            return False, "Preco invalido. Use formato numerico (ex: 630.00)."
        try:
            f = float(v)
            if f <= 0: return False, "Preco deve ser maior que zero."
            if f > 999999: return False, "Preco muito alto."
            return True, f"{f:.2f}"
        except ValueError:
            return False, "Preco invalido."

    @classmethod
    def validate_url(cls, value):
        v = cls.sanitize(value, field_type="url").strip()
        if not v: return True, ""
        if not re.match(r"^https?://[^\s<>\"]{5,500}$", v):
            return False, "URL invalida. Deve comecar com https://"
        if cls.has_injection(v): return False, "URL contem conteudo suspeito."
        return True, v

    @classmethod
    def validate_product_name(cls, value):
        v = cls.sanitize(value, field_type="product_name")
        if cls.has_injection(v): return False, "Nome do produto contem caracteres invalidos."
        if not v or len(v) < 2: return False, "Nome muito curto."
        if len(v) > 200: return False, "Nome muito longo (max 200 chars)."
        return True, v

    @classmethod
    def validate_wa_number(cls, value):
        v = re.sub(r"\D", "", cls.sanitize(value, field_type="wa_number"))
        if not v.startswith("55"): v = "55" + v
        ok, result = cls.validate_phone(v[2:])
        if not ok: return False, result
        return True, v

    @classmethod
    def validate_slug(cls, value):
        v = re.sub(r"[^a-z0-9_\-]", "", cls.sanitize(value, field_type="slug").lower())
        if len(v) < 2: return False, "Slug muito curto (minimo 2 chars)."
        if len(v) > 60: return False, "Slug muito longo (max 60 chars)."
        return True, v

    @classmethod
    def validate_field(cls, field_type, value):
        dispatch = {
            "name": cls.validate_name, "phone": cls.validate_phone,
            "cpf": cls.validate_cpf, "cep": cls.validate_cep,
            "price": cls.validate_price, "url": cls.validate_url,
            "product_name": cls.validate_product_name,
            "wa_number": cls.validate_wa_number, "slug": cls.validate_slug,
        }
        method = dispatch.get(field_type)
        if not method:
            clean = cls.sanitize(value)
            if cls.has_injection(clean): return False, "Campo contem caracteres invalidos.", field_type
            return True, clean, field_type
        ok, result = method(value)
        return ok, result, field_type


class ActivityAudit:
    CATEGORIES = {
        "admin_login":           ("\U0001f510 Login no Painel",        "admin"),
        "admin_logout":          ("\U0001f6aa Logout do Painel",       "admin"),
        "admin_config_save":     ("\u2699\ufe0f Config Salva",        "admin"),
        "admin_product_create":  ("\U0001f4e6 Produto Criado",         "admin"),
        "admin_product_update":  ("\u270f\ufe0f Produto Atualizado",  "admin"),
        "admin_product_delete":  ("\U0001f5d1 Produto Deletado",       "admin"),
        "admin_link_generate":   ("\U0001f517 Link Gerado",            "admin"),
        "admin_channel_set":     ("\U0001f4e2 Canal Configurado",      "admin"),
        "admin_shipping_set":    ("\U0001f69a Frete Configurado",      "admin"),
        "lead_page_entry":       ("\U0001f441 Visita na Pagina",       "lead"),
        "lead_captured":         ("\U0001f4dd Lead Capturado",         "lead"),
        "lead_cep_lookup":       ("\U0001f4cd CEP Consultado",         "lead"),
        "lead_pix_generated":    ("\U0001f4b8 Pix Gerado",             "lead"),
        "lead_payment_confirmed":("\u2705 Pagamento Confirmado",       "lead"),
        "lead_whatsapp_click":   ("\U0001f4f2 Click WhatsApp",         "lead"),
        "lead_buy_click":        ("\U0001f6d2 Click Comprar",          "lead"),
        "security_brute_force":  ("\U0001f6a8 Brute Force",            "security"),
        "security_bot_blocked":  ("\U0001f916 Bot Bloqueado",          "security"),
        "security_invalid_data": ("\u274c Dado Invalido Rejeitado",    "security"),
    }

    @staticmethod
    def _ensure_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                category   TEXT NOT NULL,
                actor_type TEXT NOT NULL DEFAULT 'lead',
                actor_id   TEXT,
                session_id TEXT,
                ip         TEXT,
                slug       TEXT,
                action     TEXT NOT NULL,
                details    TEXT,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_al_actor ON activity_log(actor_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_al_slug  ON activity_log(slug, created_at)")
        conn.commit()

    @classmethod
    def log(cls, category, actor_id=None, session_id=None, ip=None, slug=None, details=None):
        try:
            import bot as _bot
            conn = _bot.get_db()
            cls._ensure_table(conn)
            info = cls.CATEGORIES.get(category, (f"Event: {category}", "system"))
            action_label, actor_type = info
            conn.execute(
                "INSERT INTO activity_log(category,actor_type,actor_id,session_id,ip,slug,action,details,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (category, actor_type, str(actor_id) if actor_id else None,
                 session_id, ip, slug, action_label,
                 json.dumps(details or {}, ensure_ascii=False, default=str), time.time())
            )
            conn.commit(); conn.close()
        except Exception as e:
            logger.error(f"[AUDIT LOG] {category}: {e}")

    @classmethod
    def get_admin_activity(cls, admin_id, limit=50):
        try:
            import bot as _bot
            conn = _bot.get_db(); cls._ensure_table(conn)
            rows = conn.execute(
                "SELECT * FROM activity_log WHERE actor_id=? AND actor_type=\'admin\' ORDER BY created_at DESC LIMIT ?",
                (str(admin_id), limit)
            ).fetchall(); conn.close()
            return [cls._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[AUDIT GET] {e}"); return []

    @classmethod
    def get_lead_activity(cls, session_id=None, ip=None, slug=None, limit=50):
        try:
            import bot as _bot
            conn = _bot.get_db(); cls._ensure_table(conn)
            if session_id:
                rows = conn.execute("SELECT * FROM activity_log WHERE session_id=? AND actor_type=\'lead\' ORDER BY created_at DESC LIMIT ?", (session_id, limit)).fetchall()
            elif ip:
                rows = conn.execute("SELECT * FROM activity_log WHERE ip=? AND actor_type=\'lead\' ORDER BY created_at DESC LIMIT ?", (ip, limit)).fetchall()
            elif slug:
                rows = conn.execute("SELECT * FROM activity_log WHERE slug=? AND actor_type=\'lead\' ORDER BY created_at DESC LIMIT ?", (slug, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM activity_log WHERE actor_type=\'lead\' ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            conn.close(); return [cls._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[AUDIT LEAD] {e}"); return []

    @classmethod
    def get_global_activity(cls, hours=24, limit=100):
        try:
            import bot as _bot
            conn = _bot.get_db(); cls._ensure_table(conn)
            since = time.time() - hours * 3600
            rows = conn.execute(
                "SELECT * FROM activity_log WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (since, limit)
            ).fetchall(); conn.close()
            return [cls._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[AUDIT GLOBAL] {e}"); return []

    @staticmethod
    def _to_dict(row):
        from datetime import datetime
        d = dict(row)
        d["created_at_fmt"] = datetime.fromtimestamp(d["created_at"]).strftime("%d/%m/%Y %H:%M:%S")
        try: d["details"] = json.loads(d.get("details") or "{}")
        except: d["details"] = {}
        return d
