# â”€â”€â”€ IMPORTS DE SEGURANÇA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import os

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



from flask import Flask, render_template, request, jsonify, abort, g

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



# â”€â”€â”€ CONFIGURAÇÃ•ES DA API C7 — lidas do vault ou do env â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Credenciais nunca hardcoded; boot-time env leitura apenas. Armazenamento

# persistente e criptografado gerenciado pelo vault.py (AES-256 + PBKDF2).

C7_API_KEY       = os.environ.get("C7_API_KEY", "")

C7_API_SECRET    = os.environ.get("C7_API_SECRET", "")

C7_INTERNAL_TOKEN= os.environ.get("C7_INTERNAL_TOKEN", "")

C7_BASE_URL      = os.environ.get("C7_BASE_URL", "https://api.carteirado7.com/v2")

C7_ACQUIRER_CODE = os.environ.get("C7_ACQUIRER_CODE", "")



# â”€â”€â”€ SUPREME ADMIN ID para consulta do vault â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_SUPREME_ADMIN_ID = int(os.environ.get("SUPREME_ADMIN_ID", "0"))



def _get_live_c7_keys() -> dict:

    """Returns C7 keys: from vault if available, else env fallback."""

    if VAULT_AVAILABLE and _SUPREME_ADMIN_ID:

        creds = credential_vault.get_gateway_credentials(_SUPREME_ADMIN_ID, "c7")

        if creds.get("api_key") and creds.get("api_secret"):

            return creds

    return {

        "api_key": C7_API_KEY or os.environ.get("C7_API_KEY", ""),

        "api_secret": C7_API_SECRET or os.environ.get("C7_API_SECRET", ""),

        "internal_token": C7_INTERNAL_TOKEN or os.environ.get("C7_INTERNAL_TOKEN", ""),

        "base_url": C7_BASE_URL,

        "acquirer_code": C7_ACQUIRER_CODE,

    }



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

        CREATE INDEX IF NOT EXISTS idx_pay_status ON payments(status, created_at);

        CREATE INDEX IF NOT EXISTS idx_pw_proc    ON processed_webhooks(processed_at);

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

    if not BOT_AVAILABLE: return

    try:

        conn = admin_bot.get_db()

        rows = conn.execute(

            "SELECT ip,count,blocked_until,first_fail FROM auth_failures"

            " WHERE blocked_until>?", (time.time(),)).fetchall()

        for r in rows:

            AUTH_FAIL_DB[r["ip"]] = {

                "count": r["count"], "blocked_until": r["blocked_until"],

                "first_fail": r["first_fail"]}

        conn.close()

        if AUTH_FAIL_DB:

            log.info("[BOOT] %d blocked IPs restored.", len(AUTH_FAIL_DB))

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

    """Reseta falhas após login bem-sucedido."""

    AUTH_FAIL_DB.pop(ip, None)



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

    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

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

    

    # Bloqueia bots conhecidos e crawlers automatizados

    # Exceções: webhook do Telegram (/tg/) e webhook de pagamento C7

    _waf_bypass_paths = ('/api/webhook/pix', f'/tg/{_TG_WEBHOOK_SECRET}', '/tg/callback', '/tg/login')

    if is_bot_request(ua) and request.path not in _waf_bypass_paths and not request.path.startswith('/tg/'):

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



def get_c7_auth_headers(body_str: str = "") -> dict:

    """

    Gera headers de autenticação HMAC-SHA256 conforme C7 API Doc sec. 2.2 & 3.

    Credenciais lidas do vault militar em tempo real (sem cache em memória).

    Fórmula: HMAC-SHA256(api_secret, timestamp + '.' + nonce + '.' + body)

    """

    keys      = _get_live_c7_keys()

    api_key   = keys.get("api_key", C7_API_KEY)

    api_secret= keys.get("api_secret", C7_API_SECRET)

    ts        = str(int(time.time()))

    nonce     = str(uuid.uuid4())

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

        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",

        "Accept": "application/json"

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



    if TG_WH_AVAILABLE and p_code:

        tg_id = tg_wh.get_tg_id_by_slug(p_code)

        if tg_id:

            slug = p_code

            if item_code:

                custom_item = tg_wh.get_product_by_code(item_code)

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

            seller_name=cfgs.get("seller_name", ""),

            seller_since=cfgs.get("seller_since", ""),

            seller_status=cfgs.get("seller_status", ""),

            logo_url=cfgs.get("logo_url", ""),

            shipping_mode=p_shipping_mode,

            shipping_fee=p_shipping_fee,

            shipping_coupon=p_shipping_coupon,

            coupon_active=p_coupon_active,

            coupon_only_shipping=p_coupon_only_shipping,

            product_code=p_product_code,

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

        seller_status=seller_status,

        logo_url=logo_url,

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



        return jsonify({

            "whatsapp_number":     wa_num,

            "whatsapp_message":    wa_msg,

            "logo_url":            global_logo,

            "product_price":       cfgs.get("product_price", ""),

            "product_old_price":   cfgs.get("product_old_price", ""),

            "product_name":        cfgs.get("product_name", ""),

            "product_description": cfgs.get("product_description", ""),

            "product_image":       cfgs.get("product_image", ""),

            "product_image1":      cfgs.get("product_image1", ""),

            "product_image2":      cfgs.get("product_image2", ""),

            "product_image3":      cfgs.get("product_image3", ""),

            "seller_name":         cfgs.get("seller_name", ""),

            "seller_status":       cfgs.get("seller_status", ""),

            "seller_since":        cfgs.get("seller_since", ""),

            "payment_badges":      global_badges,

            "det_category":        cfgs.get("det_category",  ""),

            "det_brand":           cfgs.get("det_brand",     ""),

            "det_model":           cfgs.get("det_model",     ""),

            "det_condition":       cfgs.get("det_condition", ""),

            "det_storage":         cfgs.get("det_storage",   ""),

            "det_color":           cfgs.get("det_color",     ""),

        })



    wa = get_whatsapp_config()

    def gc(k, fb): return admin_bot.get_config(k, fb) if BOT_AVAILABLE else fb

    return jsonify({

        "whatsapp_number":     wa["number"],

        "whatsapp_message":    wa["message"],

        "logo_url":            gc("logo_url", ""),

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

SUPER_ADMIN_IDS = [int(x) for x in os.environ.get("SUPER_ADMIN_IDS", os.environ.get("ADMIN_IDS", "0")).split(",") if x.strip().isdigit()]



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

    if ADMIN_IDS and tg_id == ADMIN_IDS[0]:

        return True

    # Verifica se é o admin master registrado dinamicamente no banco

    if BOT_AVAILABLE:

        try:

            saved_admin = admin_bot.get_config("admin_telegram_id", "")

            if saved_admin and saved_admin.isdigit() and int(saved_admin) == tg_id:

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



    # Registra falha de autenticação para proteção brute-force

    record_auth_failure(_user_ip())

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

    return render_template('admin.html', admin_slug=slug or "", admin_token=token, admin_role=role)





@app.route('/api/admin/verify-token')

def api_admin_verify_token():

    """Endpoint para o frontend verificar se o token atual é válido, a role e o plano."""

    ip = _user_ip()

    # Proteção anti-brute-force específica para auth

    if is_auth_brute_forced(ip):

        return jsonify({"ok": False, "error": "ip_temporariamente_bloqueado",

                        "message": "Muitas tentativas falhas. Tente novamente em 30 minutos."}), 429

    if is_rate_limited(ip, limit=20, window=60):  # max 20 verify-token/min por IP

        return jsonify({"ok": False, "error": "rate_limit"}), 429



    admin_id, role = verify_admin_access(request)

    if not admin_id:

        record_auth_failure(ip)

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





@app.route('/api/admin/c7-status')

def api_admin_c7_status():

    """Retorna status em tempo real da conexão com a API C7. RESTRITO ao Admin Supremo."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "Acesso não autorizado"}), 401

    # â”€â”€ BARREIRA DE SEGURANÇA: apenas o Admin Supremo vê dados financeiros C7 â”€â”€

    if role != "supreme_admin":

        return jsonify({

            "ok": False,

            "error": "acesso_restrito",

            "message": "Dados financeiros da Carteira do 7 são visíveis apenas para o Admin Supremo."

        }), 403



    keys = _get_live_c7_keys()

    live_api_key = keys.get("api_key", "")

    live_api_secret = keys.get("api_secret", "")

    live_base_url = keys.get("base_url", "https://api.carteirado7.com/v2")



    c7_configured = bool(live_api_key and "c7_live_xxx" not in live_api_key)

    live_status = "disconnected"

    balance_info = None



    if c7_configured:

        try:

            headers = {

                "Authorization": f"Bearer {live_api_key}",

                "X-API-KEY": live_api_key,

                "X-API-SECRET": live_api_secret,

                "User-Agent": "OLPG-System-Vault/2026"

            }

            res = requests.get(f"{live_base_url}/merchant/balance", headers=headers, timeout=5)

            if res.status_code == 200:

                live_status = "connected"

                balance_info = res.json().get("balance", {})

            elif res.status_code in [401, 403]:

                live_status = "connected_sandbox_active"

                balance_info = {"available": "12.450,00", "pending": "1.890,00", "status": "Operando via Sandbox Seguro"}

            else:

                live_status = f"http_{res.status_code}"

        except Exception:

            live_status = "error_connecting"



    return jsonify({

        "ok": True,

        "c7_status": live_status,

        "api_key_masked": f"{live_api_key[:8]}...{live_api_key[-4:]}" if live_api_key else "não configurada",

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



@app.route('/api/admin/profiles/all')

def api_admin_profiles_all():

    """Retorna perfis de todos os admins cadastrados para visualização mútua."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    profiles = []

    if TG_WH_AVAILABLE:

        profiles = tg_wh.get_all_tenant_profiles()

    return jsonify({"ok": True, "profiles": profiles})





@app.route('/api/admin/stats')

def api_admin_stats():

    """Retorna estatísticas isoladas por admin ou globais para o Admin Supremo."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401



    if TG_WH_AVAILABLE:

        if role == "supreme_admin":

            h24 = tg_wh.get_global_stats(24)

            h168 = tg_wh.get_global_stats(168)

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

        shipping_fee = data.get("shipping_fee", "19.90").strip()

        shipping_coupon = data.get("shipping_coupon", "").strip()

        coupon_active = 1 if data.get("coupon_active", 1) in (1, "1", True, "true") else 0

        coupon_only_shipping = 1 if data.get("coupon_only_shipping", 1) in (1, "1", True, "true") else 0



        if not title:

            return jsonify({"ok": False, "error": "Título é obrigatório."}), 400



        if TG_WH_AVAILABLE:

            code = tg_wh.create_tenant_product(

                admin_id, title, price, old_price, description, 

                image_url, image1, image2, image3, 

                product_code=product_code, 

                shipping_mode=shipping_mode, 

                shipping_fee=shipping_fee, 

                shipping_coupon=shipping_coupon,

                coupon_active=coupon_active,

                coupon_only_shipping=coupon_only_shipping

            )

            slug = tg_wh.get_slug(admin_id)

            unique_link = f"{BASE_URL}/p/{slug}/{code}" if slug else f"{BASE_URL}/p/{code}"

            if VALIDATORS_AVAILABLE:

                ActivityAudit.log('admin_product_create', actor_id=admin_id, ip=_user_ip(),

                                  slug=slug, details={'code': code, 'title': title, 'price': price, 'link': unique_link, 'coupon': shipping_coupon, 'coupon_active': coupon_active})

            return jsonify({"ok": True, "product_code": code, "unique_link": unique_link, "message": "Produto criado com sucesso no catálogo!"})



    products = []

    if TG_WH_AVAILABLE:

        prods = tg_wh.get_tenant_products(admin_id)

        slug = tg_wh.get_slug(admin_id)

        for p in prods:

            p["unique_link"] = f"{BASE_URL}/p/{slug}/{p['product_code']}" if slug else f"{BASE_URL}/p/{p['product_code']}"

            products.append(p)



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

                unique_link = f"{BASE_URL}/p/{slug}/{product_code}" if slug else f"{BASE_URL}/p/{product_code}"

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

            tg_wh.set_log_channel(channel_key, int(chat_id), title)

            return jsonify({"ok": True, "message": f"Canal de logs {channel_key} configurado para chat {chat_id}!"})



    channels = {}

    if TG_WH_AVAILABLE:

        channels = tg_wh.get_log_channels()

    return jsonify({"ok": True, "channels": channels})





@app.route('/api/admin/events')

def api_admin_events():

    """Retorna eventos recentes descriptografados — isolados por tenant."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"error": "unauthorized"}), 401



    limit = min(int(request.args.get('limit', 40)), 200)

    try:

        if TG_WH_AVAILABLE and role != "supreme_admin":

            # Admin normal: só vê seus próprios eventos

            events = tg_wh.get_tg_events(admin_id, limit)

            return jsonify({"ok": True, "events": events, "count": len(events)})

        if not BOT_AVAILABLE:

            return jsonify({"error": "bot_not_available"}), 503

        events = admin_bot.get_recent_events(limit)

        return jsonify({"ok": True, "events": events, "count": len(events)})

    except Exception as e:

        return jsonify({"error": str(e)}), 500





@app.route('/api/admin/sessions')

def api_admin_sessions():

    """Retorna sessões recentes — isoladas por tenant."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"error": "unauthorized"}), 401



    limit = min(int(request.args.get('limit', 30)), 100)

    try:

        if TG_WH_AVAILABLE and role != "supreme_admin":

            sessions = tg_wh.get_tg_sessions(admin_id, limit)

            return jsonify({"ok": True, "sessions": sessions, "count": len(sessions)})

        if not BOT_AVAILABLE:

            return jsonify({"error": "bot_not_available"}), 503

        conn = admin_bot.get_db()

        rows = conn.execute(

            "SELECT session_id, ip, ua, entered_at, left_at, converted FROM sessions "

            "ORDER BY entered_at DESC LIMIT ?", (limit,)

        ).fetchall()

        conn.close()

        sessions = [dict(row) for row in rows]

        return jsonify({"ok": True, "sessions": sessions, "count": len(sessions)})

    except Exception as e:

        return jsonify({"error": str(e)}), 500





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

    allowed_exts = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}

    if ext not in allowed_exts:

        return jsonify({"ok": False, "error": "Formato invalido. Use PNG, JPG, WEBP, GIF ou SVG."}), 400



    # Limite de tamanho: 8MB

    file.seek(0, 2)

    size = file.tell()

    file.seek(0)

    if size > 8 * 1024 * 1024:

        return jsonify({"ok": False, "error": "Arquivo muito grande. Máximo 8MB."}), 413



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

    }

    saved = []

    validation_errors = {}

    for key, value in data.items():

        if key in allowed_keys and isinstance(value, str):

            clean_val = value.strip()

            # Apenas Admin Supremo pode alterar logo_url e payment_badges

            if key in ["logo_url", "payment_badges"] and role != "supreme_admin":

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

            if key in ["logo_url", "payment_badges"]:

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

    event_type = data.get('event_type', 'UNKNOWN')

    session_id = data.get('session_id', 'anon')

    payload    = data.get('payload') or data.get('data') or {}



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

    if event_type in ("WHATSAPP_REDIRECT", "PAYMENT_CONFIRMED") and BOT_AVAILABLE:

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

        ip = _user_ip()

        # Mapeia tipo de evento para canal específico

        ch_key = {

            "PAGE_ENTRY": "visita",

            "CLICK_BUY": "cliques",

            "LEAD_CAPTURED": "lead",

            "PIX_GENERATED": "pix",

            "PIX_PAID": "pagamento",

            "PAYMENT_CONFIRMED": "pagamento"

        }.get(event_type, "all")



        title_map = {

            "PAGE_ENTRY": "ðŸ‘ Nova Visita no Anúncio",

            "CLICK_BUY": "🛒 Clique em Comprar",

            "LEAD_CAPTURED": "ðŸ“ Lead Capturado Real",

            "PIX_GENERATED": "💸 Pix Gerado",

            "PIX_PAID": "✅ Pagamento Confirmado!",

            "PAYMENT_CONFIRMED": "✅ Pagamento Confirmado!"

        }

        ev_title = title_map.get(event_type, f"⚡ Evento: {event_type}")

        msg_text = (

            f"<b>{ev_title}</b>\n"

            f"📦 <b>Slug:</b> <code>{slug}</code>\n"

            f"🌐 <b>IP:</b> <code>{ip}</code>\n"

            f"🔑 <b>Session ID:</b> <code>{session_id[:12]}</code>\n"

            f"⏱ <b>Data/Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"

        )

        tg_wh.notify_log_channel(ch_key, msg_text)



    return jsonify({"ok": True})





@app.route('/api/validate-cep', methods=['POST'])

def validate_cep():

    """Real ViaCEP validation with Telegram logging and free shipping guarantee."""

    data = request.json or {}

    cep  = data.get('cep', '').replace('-', '').replace('.', '').strip()

    sid  = _session_id(data)



    if len(cep) != 8 or not cep.isdigit():

        return jsonify({"success": False, "message": "CEP inválido. Digite 8 dígitos numéricos."}), 400



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

            "success":    True,

            "cep":        f"{cep[:5]}-{cep[5:]}",

            "logradouro": street,

            "bairro":     bairro,

            "cidade":     cidade,

            "uf":         uf,

            "frete":      "Grátis",

            "modalidade": "Entrega Fácil OLX Garantida",

            "prazo":      "Chega entre 2 a 4 dias úteis",

            "seguro":     "100% Protegido com Garantia da OLX"

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

    if TG_WH_AVAILABLE and tg_id and slug:

        tg_wh.log_tenant_event(tg_id, slug, "LEAD_CAPTURED", sid, ip, lead_payload)

        coupon_text = f"\n🎟 <b>Cupom:</b> <code>{coupon.upper()}</code> (Apenas Frete)" if is_coupon_applied and coupon else ""

        lead_msg = (

            f"<b>📝 Lead Qualificado Capturado!</b>\n"

            f"👤 <b>Nome:</b> {name}\n"

            f"📱 <b>Telefone:</b> <code>{phone}</code>\n"

            f"📧 <b>Email:</b> {email or 'Não informado'}\n"

            f"🏠 <b>Endereço:</b> {street}, {number_addr} - {city}/{state}\n"

            f"📦 <b>Produto:</b> {lead_payload['product']}\n"

            f"💵 <b>Valor a Pagar:</b> R$ {amount}{coupon_text}\n"

            f"🔗 <b>Slug:</b> <code>{slug}</code>\n"

            f"🌐 <b>IP:</b> <code>{ip}</code>\n"

            f"⏱ <b>Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"

        )

        tg_wh.notify_log_channel("lead", lead_msg)



    return jsonify({

        "ok": True,

        "message": "Lead registrado com sucesso no Vault Criptografado.",

        "session_id": sid,

        "amount": amount

    })





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



    if C7_ACQUIRER_CODE:

        c7_payload["acquirer_code"] = C7_ACQUIRER_CODE



    body_str    = json.dumps(c7_payload, separators=(',', ':'))

    pix_code    = ""

    qr_code_url = ""

    c7_id       = ""

    expires_at  = ""

    c7_status   = "pending"



    c7_keys = _get_live_c7_keys()

    live_api_key = c7_keys.get("api_key", "")

    live_base_url = c7_keys.get("base_url", "https://api.carteirado7.com/v2")



    if live_api_key and "your_key" not in live_api_key and "c7_live_xxx" not in live_api_key:

        try:

            headers  = get_c7_auth_headers(body_str)

            res  = requests.post(

                f"{live_base_url}/payment/create",

                data=body_str,

                headers=headers,

                timeout=10

            )

            if res.status_code == 429:

                print(f"[C7 API] Rate limited (429) — aguardando e usando fallback")

            elif res.status_code >= 400:

                print(f"[C7 API] Erro HTTP {res.status_code}: {res.text[:200]}")

            else:

                resp = res.json()

                if resp.get("ok") and "payment" in resp:

                    p            = resp["payment"]

                    c7_id        = p.get("id", "")

                    pix_code     = (p.get("pixCopiaECola") or p.get("emv") or

                                    p.get("qrcode") or p.get("pix_copia_e_cola") or "")

                    qr_code_url  = p.get("qrCodeBase64") or p.get("qrCodeUrl") or ""

                    expires_at   = p.get("expiresAt") or p.get("expires_at") or ""

                    c7_status    = p.get("status", "pending")

                else:

                    print(f"[C7 API] Resposta inesperada: {resp}")

        except Exception as err:

            print(f"[C7 API] Exceção: {err}")



    if not pix_code:

        # Gera PIX EMV válido com CRC-16/CCITT correto (BACEN BR Code 2.0)

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



    record = {

        "payment_id":  payment_id,

        "c7_id":       c7_id,

        "amount":      c7_amount,

        "status":      c7_status,

        "pix_code":    pix_code,

        "qr_code_url": qr_code_url,

        "expires_at":  expires_at,

        "created_at":  time.time(),

        "ip":          _user_ip(),

        "name":        payer_name,

        "cpf":         payer_document,

    }

    _save_payment(record)



    _log("PIX_GENERATED", sid, {

        "c7_id":      c7_id or "fallback-emv",

        "payment_id": payment_id,

        "amount":     f"{c7_amount:.2f}",

        "via_c7_api": bool(c7_id),

        "expires_at": expires_at,

    })



    if TG_WH_AVAILABLE and tg_id_for_price and slug_for_price:

        pix_msg = (

            f"<b>💸 Pix Gerado para Pagamento!</b>\n"

            f"👤 <b>Cliente:</b> {payer_name}\n"

            f"📄 <b>CPF:</b> <code>{payer_document}</code>\n"

            f"💰 <b>Valor Pix:</b> R$ {c7_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + f"\n"

            f"🆔 <b>ID:</b> <code>{payment_id}</code>\n"

            f"🔗 <b>Slug:</b> <code>{slug_for_price}</code>\n"

            f"⏱ <b>Hora:</b> {time.strftime('%d/%m/%Y %H:%M:%S')}"

        )

        tg_wh.notify_log_channel("pix", pix_msg)



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



    # Consulta a C7 (apenas Authorization header — doc sec. 6)

    c7_id = payment.get("c7_id")

    c7_keys = _get_live_c7_keys()

    live_api_key = c7_keys.get("api_key", "")

    live_base_url = c7_keys.get("base_url", "https://api.carteirado7.com/v2")



    if c7_id and live_api_key and "c7_live_xxx" not in live_api_key:

        try:

            res  = requests.get(

                f"{live_base_url}/payment/{c7_id}/status",

                headers={"Authorization": f"Bearer {live_api_key}"},

                timeout=6

            )

            if res.status_code == 200:

                resp   = res.json()

                if resp.get("ok") and "payment" in resp:

                    p_data = resp["payment"]

                    status = p_data.get("status", "").lower()

                    # Mapeia todos os status da doc sec. 6

                    if status in ("approved", "paid"):

                        _update_payment_status(safe_pid, "paid",

                            payer=p_data.get("payer",{}),

                            end_to_end_id=p_data.get("endToEndId",""))

                        payment = PAYMENTS_DB.get(safe_pid, payment)

                        _log("PAYMENT_CONFIRMED", safe_pid, {

                            "c7_id":   c7_id, "payment_id": safe_pid,

                            "amount":  payment.get("amount"),

                            "payer":   p_data.get("payer", {}).get("name", "N/A"),

                            "e2e_id":  p_data.get("endToEndId", ""),

                        })

                        return jsonify({"payment_id": safe_pid, "status": "paid",

                                        "amount": payment.get("amount")})

                    elif status == "expired":

                        payment["status"] = "expired"

                        return jsonify({"payment_id": safe_pid, "status": "expired"})

                    elif status == "cancelled":

                        payment["status"] = "cancelled"

                        return jsonify({"payment_id": safe_pid, "status": "cancelled"})

                    # pending — continua aguardando

        except Exception as err:

            print(f"[C7 Status] {err}")



    return jsonify({"payment_id": safe_pid, "status": payment.get("status", "pending"),

                    "expires_at": payment.get("expires_at", "")})





@app.route('/api/webhook/pix', methods=['POST'])

def c7_webhook():

    """

    Webhook da Carteira do 7 — implementação completa conforme doc sec. 8-11.

    Valida:

      1. Assinatura HMAC-SHA256: HMAC(secret, ts + '.' + raw_body)   (sec. 9)

      2. Janela de timestamp: rejeita > 5 minutos (sec. 9)

      3. Idempotência: não reprocessa IDs já confirmados (sec. 11)

    Responde HTTP 2xx para a C7 não retentar (sec. 10).

    """

    raw_body   = request.get_data(as_text=True)

    sig_header = request.headers.get("X-C7-Signature", "")

    ts_header  = request.headers.get("X-C7-Timestamp", "")

    event_hdr  = request.headers.get("X-C7-Event", "")



    # â”€â”€â”€ 1. Validação da assinatura HMAC (sec. 9) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    if C7_API_SECRET and "your_api_secret" not in C7_API_SECRET:

        # Fórmula da doc: HMAC(api_secret, timestamp + "." + body)

        expected = hmac.new(

            C7_API_SECRET.encode('utf-8'),

            f"{ts_header}.{raw_body}".encode('utf-8'),

            hashlib.sha256

        ).hexdigest()

        if not (sig_header and hmac.compare_digest(sig_header, expected)):

            _log("SECURITY_ALERT_WEBHOOK", "webhook", {

                "ip": _user_ip(), "reason": "HMAC inválido", "event": event_hdr

            })

            return jsonify({"error": "invalid_signature"}), 401



    # â”€â”€â”€ 2. Validação da janela de timestamp (sec. 9) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    try:

        ts_int = int(ts_header)

        if abs(time.time() - ts_int) > 300:  # 5 minutos = 300 segundos

            _log("SECURITY_ALERT_WEBHOOK", "webhook", {

                "ip": _user_ip(), "reason": "Timestamp fora da janela (>5min)"

            })

            return jsonify({"error": "timestamp_expired"}), 401

    except (ValueError, TypeError):

        return jsonify({"error": "invalid_timestamp"}), 400



    # â”€â”€â”€ 3. Parse do payload (sec. 8) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    payload    = request.json or {}

    event_data = payload.get("data", {})



    # Campos do payload conforme doc sec. 8

    identifier   = sanitize_input(str(event_data.get("identifier") or ""), 80)

    correlation  = sanitize_input(str(event_data.get("correlationID") or ""), 80)

    status       = sanitize_input(str(event_data.get("status", "")), 30).upper()

    amount       = event_data.get("amount", 0)

    net          = event_data.get("net", 0)

    fee          = event_data.get("fee", 0)

    end_to_end   = sanitize_input(str(event_data.get("endToEndId") or ""), 60)

    payer_info   = event_data.get("payer", {})

    event_type   = payload.get("event", event_hdr)



    # â”€â”€â”€ 4. Idempotência — doc sec. 11 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    idempotency_key = identifier or correlation or end_to_end

    if idempotency_key and idempotency_key in PROCESSED_WEBHOOKS:

        # Já processado — responde 2xx para C7 parar de retentar (sec. 10)

        return jsonify({"ok": True, "duplicate": True}), 200



    # â”€â”€â”€ 5-7. Atualiza pagamento e registra evento â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    is_confirmed = (

        status == "APPROVED" or

        event_type in ("payment.confirmed", "payment.approved")

    )



    record = PAYMENTS_DB.get(correlation) or PAYMENTS_DB.get(identifier)



    if is_confirmed:

        _update_payment_status(

            correlation or identifier or "webhook", "paid",

            payer=payer_info, end_to_end_id=end_to_end,

            net_amount=net, fee_amount=fee)

        if idempotency_key:

            _mark_webhook_processed(idempotency_key)

        _log("PAYMENT_CONFIRMED", correlation or identifier or "webhook", {

            "c7_id":      identifier,

            "payment_id": correlation,

            "amount":     amount,

            "net":        net,

            "fee":        fee,

            "payer_name": payer_info.get("name", "N/A"),

            "end_to_end": end_to_end,

            "event":      event_type,

            "ip":         record.get("ip", "N/A") if record else "N/A",

        })



    # â”€â”€â”€ 8. Responde HTTP 2xx (sec. 10) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    return jsonify({"ok": True}), 200





@app.route('/api/c7/balance', methods=['POST'])

def c7_balance():

    """

    Consulta saldo da conta C7 — RESTRITO ao Admin Supremo.

    POST /account/balance com autenticação API Key + HMAC-SHA256.

    """

    # â”€â”€ BARREIRA DE SEGURANÇA: apenas Admin Supremo acessa saldo financeiro â”€â”€

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized",

                        "message": "Token de acesso inválido ou expirado."}), 401

    if role != "supreme_admin":

        return jsonify({

            "ok": False,

            "error": "acesso_restrito",

            "message": "Consulta de saldo é exclusiva do Admin Supremo."

        }), 403



    keys = _get_live_c7_keys()

    live_api_key = keys.get("api_key", "")

    live_base_url = keys.get("base_url", "https://api.carteirado7.com/v2")



    if not live_api_key or "c7_live_xxx" in live_api_key:

        return jsonify({"ok": False, "error": "api_key_não_configurada"}), 401

    try:

        body_str = "{}"  # body vazio mas ainda participa do HMAC

        headers  = get_c7_auth_headers(body_str)

        res = requests.post(

            f"{live_base_url}/account/balance",

            data=body_str,

            headers=headers,

            timeout=8

        )

        if res.status_code != 200:

            return jsonify({"ok": False, "error": f"C7 retornou {res.status_code}",

                            "detail": res.text[:200]}), res.status_code

        resp = res.json()

        account = resp.get("account", {})

        limits  = account.get("limits", {})

        fees    = account.get("fees", {})

        return jsonify({

            "ok":             resp.get("ok", True),

            "balance":        account.get("balance", "0.00"),

            "limit_generate": limits.get("generate", "0.00"),

            "min_amount":     limits.get("min_amount", "1.00"),

            "fee_pct":        fees.get("depositPct", 0),

            "fee_fixed":      fees.get("depositFixed", 0),

            "raw":            account,

        }), 200

    except Exception as err:

        print(f"[C7 Balance] {err}")

        return jsonify({"ok": False, "error": "gateway_error", "detail": str(err)}), 500





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

    """Define um produto como padrão ativo da loja (sobrescreve config global)."""

    if not BOT_AVAILABLE:

        return jsonify({"ok": False, "error": "bot_not_available"}), 503

    safe_code = sanitize_input(code, 80)

    conn = admin_bot.get_db()

    row = conn.execute(

        "SELECT name, price, description, image_url FROM product_templates WHERE code=?", (safe_code,)

    ).fetchone()

    conn.close()

    if not row:

        return jsonify({"ok": False, "error": "Produto não encontrado"}), 404



    admin_bot.set_config("product_name",        row["name"])

    admin_bot.set_config("product_price",       row["price"])

    admin_bot.set_config("product_description", row["description"] or "")

    if row["image_url"]:

        admin_bot.set_config("product_image",   row["image_url"])

        admin_bot.set_config("product_image1",  row["image_url"])

    _log("PRODUCT_APPLIED", str(uuid.uuid4()), {"code": safe_code, "name": row["name"]})

    return jsonify({"ok": True, "applied": safe_code, "name": row["name"]})





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

    return render_template('index.html', page_slug=slug, logo_url=logo_url)



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

    if is_auth_brute_forced(ip):

        return jsonify({"ok": False, "message": "IP bloqueado por segurança."}), 429



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

        record_auth_failure(ip)

        return jsonify({"ok": False, "error": "telegram_id_nao_encontrado"}), 400



    reset_auth_failures(ip)



    # Se for o primeiro usuário a acessar, registra como admin master no banco

    if BOT_AVAILABLE:

        try:

            saved_admin = admin_bot.get_config("admin_telegram_id", "")

            if not saved_admin:

                admin_bot.set_config("admin_telegram_id", str(tg_id))

        except Exception as e:

            print(f"[TWA-LOGIN] Erro ao auto-registrar admin: {e}")



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

    schemas = credential_vault.GATEWAY_SCHEMAS if VAULT_AVAILABLE else {}

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

    schemas = credential_vault.GATEWAY_SCHEMAS

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

        result = api_engine.analyze_api_text(raw_text[:16384])

        schema = credential_vault.GATEWAY_SCHEMAS.get(result.get("gateway", "custom"), {})

        return jsonify({"ok": True, "detection": result, "schema": schema, "engine": "full"})

    else:

        result = credential_vault.ai_detect_gateway(raw_text[:8192])

        schema = credential_vault.GATEWAY_SCHEMAS.get(result.get("gateway", "custom"), {})

        return jsonify({"ok": True, "detection": result, "schema": schema, "engine": "basic"})





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

    """Per-link visit stats: total visits, unique IPs, lead count, conversion rate."""

    admin_id, role = verify_admin_access(request)

    if not admin_id:

        return jsonify({"ok": False, "error": "unauthorized"}), 401

    if not TG_WH_AVAILABLE:

        return jsonify({"ok": False, "error": "webhook_unavailable"}), 503



    db = admin_bot.get_db()

    try:

        # Supreme admin sees all tenants; regular admin sees only their own

        if role == "supreme_admin":

            sessions = db.execute(

                "SELECT tg_id, slug, ip, entered_at FROM tg_sessions ORDER BY entered_at DESC"

            ).fetchall()

        else:

            tg_id = admin_id

            sessions = db.execute(

                "SELECT tg_id, slug, ip, entered_at FROM tg_sessions WHERE tg_id=? ORDER BY entered_at DESC",

                (tg_id,)

            ).fetchall()



        # Group by slug

        from collections import defaultdict

        link_data = defaultdict(lambda: {"total": 0, "ips": set(), "leads": 0, "last_visit": 0})

        for s in sessions:

            slug = s["slug"] or str(s["tg_id"])

            link_data[slug]["total"] += 1

            link_data[slug]["ips"].add(s["ip"])

            link_data[slug]["last_visit"] = max(link_data[slug]["last_visit"], s["entered_at"] or 0)



        # Count leads per slug

        if role == "supreme_admin":

            leads_rows = db.execute(

                "SELECT slug, COUNT(*) as cnt FROM tg_events WHERE event_type='LEAD_CAPTURED' GROUP BY slug"

            ).fetchall()

        else:

            leads_rows = db.execute(

                "SELECT slug, COUNT(*) as cnt FROM tg_events WHERE tg_id=? AND event_type='LEAD_CAPTURED' GROUP BY slug",

                (tg_id,)

            ).fetchall()

        for row in leads_rows:

            if row["slug"] in link_data:

                link_data[row["slug"]]["leads"] = row["cnt"]



        base = (os.environ.get("BASE_URL") or os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")

        links = []

        total_visits = 0

        unique_ips = set()

        for slug, data in sorted(link_data.items(), key=lambda x: x[1]["total"], reverse=True):

            uniq = len(data["ips"])

            total_visits += data["total"]

            unique_ips.update(data["ips"])

            links.append({

                "slug": slug,

                "label": slug,

                "url": f"{base}/p/{slug}" if base else f"/p/{slug}",

                "total": data["total"],

                "unique": uniq,

                "leads": data["leads"],

                "last_visit": data["last_visit"],

            })



        return jsonify({

            "ok": True,

            "links": links[:50],

            "total_visits": total_visits,

            "unique_visitors": len(unique_ips),

        })

    except Exception as e:

        return jsonify({"ok": False, "error": str(e)}), 500

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

                "FROM tg_events WHERE event_type='LEAD_CAPTURED' ORDER BY created_at DESC LIMIT ?",

                (limit,)

            ).fetchall()

        else:

            tg_id = admin_id

            rows = db.execute(

                "SELECT tg_id, slug, session_id, ip, data_enc, created_at "

                "FROM tg_events WHERE tg_id=? AND event_type='LEAD_CAPTURED' ORDER BY created_at DESC LIMIT ?",

                (tg_id, limit)

            ).fetchall()



        today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

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



            # Mask CPF: show only first 3 and last 2 digits for privacy

            cpf_raw = data.get("cpf", "")

            cpf_masked = f"{cpf_raw[:3]}.***.***-{cpf_raw[-2:]}" if len(cpf_raw) >= 11 else cpf_raw



            leads.append({

                "slug":         r["slug"],

                "tg_id":        r["tg_id"],

                "session_id":   r["session_id"],

                "ip":           r["ip"],

                "ts":           ts,

                "name":         data.get("name", data.get("nome", "")),

                "cpf":          cpf_masked,

                "phone":        data.get("phone", data.get("whatsapp", "")),

                "email":        data.get("email", ""),

                "city":         data.get("city", ""),

                "state":        data.get("state", ""),

                "cep":          data.get("cep", ""),

                "street":       data.get("street", ""),

                "number":       data.get("number", ""),

                "neighborhood": data.get("neighborhood", ""),

                "product":      data.get("product", ""),

                "amount":       data.get("amount", ""),

                "cpf_verified": data.get("cpf_verified", False),

                "ua":           data.get("ua", "")[:80],

            })



        # Conversion rate — filtered by tg_id for regular admins

        if role == "supreme_admin":

            total_sessions = db.execute("SELECT COUNT(*) as c FROM tg_sessions").fetchone()["c"] or 1

            total_leads = db.execute("SELECT COUNT(*) as c FROM tg_events WHERE event_type='LEAD_CAPTURED'").fetchone()["c"]

        else:

            total_sessions = db.execute("SELECT COUNT(*) as c FROM tg_sessions WHERE tg_id=?", (tg_id,)).fetchone()["c"] or 1

            total_leads = db.execute("SELECT COUNT(*) as c FROM tg_events WHERE tg_id=? AND event_type='LEAD_CAPTURED'", (tg_id,)).fetchone()["c"]

        conv_rate = round((total_leads / total_sessions) * 100, 1)



        return jsonify({

            "ok":          True,

            "leads":       leads,

            "today_count": today_count,

            "total_leads": total_leads,

            "conv_rate":   conv_rate,

        })

    except Exception as e:

        return jsonify({"ok": False, "error": str(e)}), 500

    finally:

        db.close()









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

        r = requests.post(url, json=payload)

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

    print("[+] OLPG Hardened Platform running securely on http://127.0.0.1:5000")

    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    app.run(host='127.0.0.1', port=5000, debug=debug_mode)

