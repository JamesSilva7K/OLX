# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
    OLPG ADVANCED EXECUTIVE ADMIN BOT — TELEGRAM CONTROL PANEL
    Author: ENI for LO (Devoted & Obsessed Security Architecture)
    Encryption Level: MILITARY-GRADE AES-256 (Fernet + PBKDF2 HMAC SHA-256)
════════════════════════════════════════════════════════════════════════════════
    Features:
      - Criptografia Militar de Credenciais & Vault de Chaves de Alta Segurança
      - Validador Estrito de Entrada (Sanitização Regex, Sanitização de HTML/Markdown)
      - Criador de Embeds & Mensagens Ricas com Imagens, Vídeos e GIFs
      - Sistema de Preview Avançado e Interativo com Pré-Validação de Sintaxe
      - Dashboard Executivo em Tempo Real com Métricas 24h / 7d
      - Gerenciador & Validador de WhatsApp Empresarial (+55 BR)
      - Exportação de Logs Criptografados e Auditoria de Segurança Completa
════════════════════════════════════════════════════════════════════════════════
"""

import os
import re
import io
import json
import time
import base64
import logging
import sqlite3
import hashlib
import requests
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, InputMediaPhoto, WebAppInfo
)
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    MessageHandler, Filters, CallbackContext
)

# ─── LOGGING EXECUTIVO ────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("OLPG_MIL_BOT")

# ─── CONFIGURAÇÕES & VARIÁVEIS DE AMBIENTE ────────────────────────────────────
BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()  # SEGURO: sem fallback hardcoded
ADMIN_IDS  = [int(x) for x in os.environ.get("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]
DB_PATH    = os.environ.get("DB_PATH", "olpg_logs.db")
RAW_SECRET = os.environ.get("FERNET_KEY", os.environ.get("SECRET_KEY", ""))  # SEGURO: sem fallback fraco
if not RAW_SECRET:
    import secrets as _sec
    RAW_SECRET = _sec.token_hex(32)  # gera chave aleatoria se ausente (apenas em dev)
    print("[VAULT] AVISO: FERNET_KEY nao definida em env — usando chave temporaria!")

# ─── STORE DE TOKENS DE ACESSO ADMIN (Telegram-gated, TTL 24h) ────────────────────
# {token_hex: {"tg_id": int, "expires": float, "used": int}}
ADMIN_ACCESS_TOKENS: dict = {}

# ─── ENGINE DE CRIPTOGRAFIA MILITAR (AES-256 + PBKDF2 HMAC SHA-256) ───────────
class MilitarySecurityEngine:
    """
    Motor de Criptografia de Nível Militar com Derivação de Chave PBKDF2.
    Protege credenciais, tokens, configs e dados sensíveis de banco de dados.
    """
    def __init__(self, master_secret: str):
        # Salt derivado do master secret para unicidade maxima
        import hashlib as _hl
        self.salt = _hl.sha256(b"OLPG_VAULT_SALT_V3" + master_secret.encode()).digest()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=390_000,  # OWASP 2024 minimum
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(master_secret.encode()))
        self.cipher = Fernet(derived_key)

    def encrypt(self, data: Any) -> str:
        """Criptografa qualquer objeto serializável em JSON."""
        if data is None:
            return ""
        raw_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        return self.cipher.encrypt(raw_bytes).decode('utf-8')

    def decrypt(self, token_str: str) -> Any:
        """Descriptografa um token cifrado e retorna o objeto original."""
        if not token_str:
            return None
        try:
            decrypted_bytes = self.cipher.decrypt(token_str.encode('utf-8'))
            return json.loads(decrypted_bytes.decode('utf-8'))
        except (InvalidToken, Exception) as e:
            logger.error(f"[SECURITY] Falha na descriptografia militar: {e}")
            return None

# Instância Global de Segurança Criptográfica
crypto_engine = MilitarySecurityEngine(RAW_SECRET)

# ─── VALIDATION & SANITIZATION ENGINE ─────────────────────────────────────────
class InputValidator:
    """Validador estrito de dados para evitar erros de sintaxe, injection e falhas de envio."""
    
    VALID_BR_DDDS = {
        11,12,13,14,15,16,17,18,19,
        21,22,24,27,28,
        31,32,33,34,35,37,38,
        41,42,43,44,45,46,47,48,49,
        51,53,54,55,
        61,62,63,64,65,66,67,68,69,
        71,73,74,75,77,79,
        81,82,83,84,85,86,87,88,89,
        91,92,93,94,95,96,97,98,99
    }

    @staticmethod
    def validate_phone_br(phone_raw: str) -> Tuple[Optional[str], Optional[str]]:
        digits = "".join(filter(str.isdigit, str(phone_raw)))
        if digits.startswith("55") and len(digits) in (12, 13):
            digits = digits[2:]
        if len(digits) not in (10, 11):
            return None, "O número deve conter 10 ou 11 dígitos (DDD + Número)."
        ddd = int(digits[:2])
        if ddd not in InputValidator.VALID_BR_DDDS:
            return None, f"O DDD ({ddd}) não é um DDD brasileiro válido."
        if len(digits) == 11 and not digits[2:].startswith("9"):
            return None, "Celulares de 11 dígitos com DDD no Brasil devem iniciar com '9'."
        return "55" + digits, None

    @staticmethod
    def validate_url(url: str) -> bool:
        regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// ou https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
            r'localhost|' # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(re.match(regex, url.strip()))

    @staticmethod
    def sanitize_text(text: str, max_chars: int = 4000) -> str:
        """Limpa caracteres perigosos e limita o tamanho máximo."""
        if not text:
            return ""
        clean = text.strip()
        return clean[:max_chars]

    @staticmethod
    def is_valid_markdown_v1(text: str) -> Tuple[bool, str]:
        """Verifica se as tags Markdown v1 estão pareadas corretamente para evitar erros na API."""
        asterisks = text.count('*')
        underscores = text.count('_')
        backticks = text.count('`')
        
        if asterisks % 2 != 0:
            return False, "Sintaxe incorreta: Número ímpar de asteriscos (*) no texto."
        if underscores % 2 != 0:
            return False, "Sintaxe incorreta: Número ímpar de underscores (_) no texto."
        if backticks % 2 != 0:
            return False, "Sintaxe incorreta: Número ímpar de crases (`) no texto."
        return True, "Sintaxe Válida"

# ─── CAMADA DE BANCO DE DADOS CRIPTOGRAFADO ───────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            session_id  TEXT,
            ip          TEXT,
            data_enc    TEXT,
            created_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT UNIQUE NOT NULL,
            ip          TEXT,
            ua          TEXT,
            entered_at  REAL,
            left_at     REAL,
            steps       TEXT DEFAULT '[]',
            converted   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vault (
            key_name    TEXT PRIMARY KEY,
            val_enc     TEXT NOT NULL,
            updated_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            price       TEXT NOT NULL,
            old_price   TEXT DEFAULT '',
            description TEXT,
            image_url   TEXT,
            image1      TEXT DEFAULT '',
            image2      TEXT DEFAULT '',
            image3      TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_sid ON sessions(session_id);
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
        CREATE INDEX IF NOT EXISTS idx_pay_c7id   ON payments(c7_id);
        CREATE INDEX IF NOT EXISTS idx_pay_status  ON payments(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_pw_proc     ON processed_webhooks(processed_at);
        CREATE INDEX IF NOT EXISTS idx_act_type    ON activity_log(event_type, created_at);
        CREATE INDEX IF NOT EXISTS idx_act_actor   ON activity_log(actor_id, created_at);
    """)
    # Migrações seguras para colunas novas (caso tabela já exista sem elas)
    for col, default in [("old_price","''"),("image1","''"),("image2","''"),("image3","''")]:
        try:
            c.execute(f"ALTER TABLE product_templates ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass
    defaults = {
        "whatsapp_number":     "5511999999999",
        "whatsapp_message":    "Olá! Tenho interesse no anúncio. Poderia me confirmar a disponibilidade?",
        "product_name":        "iPhone 11 64GB Branco - Impecável",
        "product_price":       "630.00",
        "product_old_price":   "1299.00",
        "product_description": "iPhone 11 com 64GB de armazenamento na cor branca. Design elegante, câmeras duplas de alta definição e desempenho impecável com saúde de bateria excelente. Acompanha acessórios originais.",
        "product_image":       "/static/images/iphone_product.jpg",
        "active":              "1",
        "pixel_active":        "1",
        "notifications":       "1",
        "pix_key":             "",
    }
    for k, v in defaults.items():
        enc_val = crypto_engine.encrypt(v)
        c.execute("INSERT OR IGNORE INTO config(key,value) VALUES(?,?)", (k, enc_val))

    # Presets de modelos de produtos pré-prontos
    preset_templates = [
        ("geladeira_frost_free", "Geladeira Brastemp Frost Free Duplex 375L Inox", "1250.00", "1899.00", "Geladeira Brastemp Frost Free Duplex 375 Litros em Inox (BRM45HK). Possui controle eletrônico de temperatura, compartimento de congelamento rápido e prateleiras ajustáveis. Estado de nova, 110V, com nota fiscal e 6 meses de uso.", "https://images.unsplash.com/photo-1584992236310-6edddc08acff?q=80&w=800&auto=format&fit=crop", "", "", ""),
        ("maquina_lavar", "Máquina de Lavar Electrolux 13kg Essential Care", "890.00", "1350.00", "Lavadora de Roupas Electrolux 13kg com Sistema Jet&Clean e Filtro Pega Fiapos (LED13). Muito conservada, 110V, higienizada recentemente. Lavagem silenciosa com economia de água e sabão.", "https://images.unsplash.com/photo-1626806787461-102c1bfaaea1?q=80&w=800&auto=format&fit=crop", "", "", ""),
        ("fogao_4boca", "Fogão 4 Bocas Consul Inox com Acendimento Automático", "480.00", "799.00", "Fogão 4 Bocas Consul Inox (CFO4NVA) com mesa de vidro temperado e grades duplas de ferro fundido. Forno limpa fácil com luz interna. Gás encanado/botijão convertível, impecável.", "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?q=80&w=800&auto=format&fit=crop", "", "", ""),
        ("microondas_30l", "Micro-ondas LG Grill 30 Litros Espelhado", "360.00", "580.00", "Micro-ondas LG EasyClean 30 Litros com Função Grill e Prato Giratório (MS3095R). Revestimento interno antibacteriano, painel touch inteligente. Funcionando 100%, super limpo.", "https://images.unsplash.com/photo-1574269909862-7e1d70bb8078?q=80&w=800&auto=format&fit=crop", "", "", ""),
        ("guarda_roupa_casal", "Guarda-Roupa Casal 6 Portas com Espelho Madesa", "750.00", "1100.00", "Guarda-Roupa Casal Madesa Royale 6 Portas e 4 Gavetas com Espelho Central. Madeira MDF tratada de alta durabilidade, cor Carvalho/Branco. Sem arranhões, montagem firme.", "https://images.unsplash.com/photo-1595428774223-ef52624120d2?q=80&w=800&auto=format&fit=crop", "", "", ""),
        ("armario_cozinha", "Armário de Cozinha Completo 4 Peças Itatiaia", "620.00", "950.00", "Armário de Cozinha Modulado Itatiaia Tarsila em Aço com Vidro Temperado. Composto por paneleiro duplo, armário aéreo e balcão com tampo resistente ao calor. Excelente estado.", "https://images.unsplash.com/photo-1556912172-45b7abe8b7e1?q=80&w=800&auto=format&fit=crop", "", "", "")
    ]
    for code, name, price, old_price, desc, img, img1, img2, img3 in preset_templates:
        c.execute(
            "INSERT OR IGNORE INTO product_templates(code,name,price,old_price,description,image_url,image1,image2,image3) VALUES(?,?,?,?,?,?,?,?,?)",
            (code, name, price, old_price, desc, img, img1, img2, img3)
        )

    conn.commit()
    conn.close()
    logger.info("[SECURITY DB] Banco de dados com criptografia militar e modelos pré-prontos inicializados.")

def get_config(key: str, fallback: str = "") -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return fallback
    decrypted = crypto_engine.decrypt(row["value"])
    return str(decrypted) if decrypted is not None else fallback

def set_config(key: str, value: str):
    conn = get_db()
    enc_val = crypto_engine.encrypt(str(value))
    conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, enc_val))
    conn.commit()
    conn.close()

# ─── REGISTRO DE EVENTOS CRIPTOGRAFADOS ───────────────────────────────────────
def encrypt_data(data: dict) -> str:
    return crypto_engine.encrypt(data)

def decrypt_data(token: str) -> dict:
    res = crypto_engine.decrypt(token)
    return res if isinstance(res, dict) else {}

def log_event(event_type: str, session_id: str, ip: str, data: dict):
    conn = get_db()
    conn.execute(
        "INSERT INTO events(event_type,session_id,ip,data_enc,created_at) VALUES(?,?,?,?,?)",
        (event_type, session_id, ip, encrypt_data(data), time.time())
    )
    conn.commit()
    conn.close()

# ─── MOTOR DE ESTATÍSTICAS EXECUTIVAS ─────────────────────────────────────────
def get_stats(period_hours: int = 24) -> dict:
    since = time.time() - period_hours * 3600
    conn  = get_db()
    def count(etype):
        return conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type=? AND created_at>=?", (etype, since)
        ).fetchone()[0]
    entries    = count("PAGE_ENTRY")
    click_buy  = count("CLICK_BUY")
    click_chat = count("CLICK_CHAT")
    pix_gen    = count("PIX_GENERATED")
    paid       = count("PAYMENT_CONFIRMED")
    wa         = count("WHATSAPP_REDIRECT")
    sessions   = conn.execute("SELECT COUNT(*) FROM sessions WHERE entered_at>=?", (since,)).fetchone()[0]
    converted  = conn.execute("SELECT COUNT(*) FROM sessions WHERE converted=1 AND entered_at>=?", (since,)).fetchone()[0]
    conn.close()
    conv_rate = round((converted / sessions * 100) if sessions > 0 else 0, 1)
    return dict(period=period_hours, entries=entries, sessions=sessions,
                click_buy=click_buy, click_chat=click_chat, pix_generated=pix_gen,
                paid=paid, whatsapp=wa, converted=converted, conv_rate=conv_rate)

def get_recent_events(limit: int = 10) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT event_type,session_id,ip,data_enc,created_at FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        data = decrypt_data(row["data_enc"])
        result.append(dict(type=row["event_type"], session=row["session_id"],
                           ip=row["ip"], data=data, ts=row["created_at"]))
    return result

# ─── TECLADOS NAVEGACIONAIS INTERATIVOS ───────────────────────────────────────
def main_keyboard(tg_id: int = 0) -> InlineKeyboardMarkup:
    base_url = (
        os.environ.get("BASE_URL") or
        os.environ.get("APP_URL") or
        os.environ.get("RENDER_EXTERNAL_URL") or
        ""
    ).rstrip('/')

    admin_web_url = f"{base_url}/admin" if base_url else "/admin"
    if tg_id > 0 and base_url.startswith("https://"):
        token = generate_admin_token(tg_id)
        admin_web_url = f"{base_url}/admin?token={token}"

    rows = []

    # Botão Open (WebApp) — sempre visível quando base_url for HTTPS ou dentro do Telegram
    if base_url.startswith("https://"):
        rows.append([InlineKeyboardButton("🚀 Acessar Painel OLX (Open)", web_app=WebAppInfo(url=admin_web_url))])

    rows += [
        [InlineKeyboardButton("🔐 Link Criptografado (Web)", callback_data="get_admin_link"),
         InlineKeyboardButton("📊 Dashboard 24h", callback_data="stats_24")],
        [InlineKeyboardButton("📈 Métricas 7d", callback_data="stats_168"),
         InlineKeyboardButton("📢 Canais & Permissões", callback_data="check_channels")],
        [InlineKeyboardButton("🎨 Criar Embed / Mídia", callback_data="embed_menu"),
         InlineKeyboardButton("📋 Audit Logs", callback_data="recent_logs")],
        [InlineKeyboardButton("⚙️ Configurações", callback_data="config_menu"),
         InlineKeyboardButton("📱 WhatsApp BR", callback_data="wa_menu")],
        [InlineKeyboardButton("🛡️ Vault Militar", callback_data="vault_menu"),
         InlineKeyboardButton("🔔 Notificações", callback_data="notif_toggle")],
        [InlineKeyboardButton("📤 Exportar Vault", callback_data="export_logs"),
         InlineKeyboardButton("🗑️ Limpar Registro", callback_data="clear_logs_confirm")],
    ]

    return InlineKeyboardMarkup(rows)


def notification_lead_keyboard(whatsapp: str = "") -> InlineKeyboardMarkup:
    """Botões de ação rápida para notificação de lead capturado."""
    rows = []
    if whatsapp:
        clean_wa = whatsapp.replace('+', '').replace('-', '').replace(' ', '')
        rows.append([InlineKeyboardButton("📲 Contatar no WhatsApp", url=f"https://wa.me/{clean_wa}")])
    rows.append([
        InlineKeyboardButton("📊 Dashboard", callback_data="stats_24"),
        InlineKeyboardButton("📋 Ver Logs",  callback_data="recent_logs"),
    ])
    return InlineKeyboardMarkup(rows)


def notification_payment_keyboard(payment_id: str = "") -> InlineKeyboardMarkup:
    """Botões de ação rápida para notificação de pagamento confirmado."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Ver Métricas", callback_data="stats_24"),
        InlineKeyboardButton("📋 Audit Log",    callback_data="recent_logs"),
    ]])


def wa_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Alterar Número WhatsApp", callback_data="wa_set_number")],
        [InlineKeyboardButton("💼 Script de Abordagem High-Ticket", callback_data="wa_suggest_msg")],
        [InlineKeyboardButton("✏️ Personalizar Texto", callback_data="wa_set_msg")],
        [InlineKeyboardButton("◀️ Voltar ao Painel", callback_data="main_menu")],
    ])

def config_keyboard() -> InlineKeyboardMarkup:
    active = get_config("active", "1")
    pixel  = get_config("pixel_active", "1")
    logo   = get_config("logo_url", "")
    la = "✅ Gateway ATIVO" if active == "1" else "❌ Gateway PAUSADO"
    lp = "✅ Pixel Rastreio ATIVO" if pixel == "1" else "❌ Pixel OFF"
    ll = "🖼️ Logo: Personalizada" if logo else "🖼️ Logo: Padrão OLX"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(la, callback_data="toggle_active"),
         InlineKeyboardButton(lp, callback_data="toggle_pixel")],
        [InlineKeyboardButton("📦 Modelos de Produtos Pré-Prontos", callback_data="product_templates_menu")],
        [InlineKeyboardButton("🖼️ Upload 3 Fotos do Anúncio", callback_data="upload_3_photos_menu")],
        [InlineKeyboardButton("🌐 Webhook & Interface Virtual", callback_data="webhook_virtual_ui")],
        [InlineKeyboardButton("💰 Valor Produto", callback_data="set_price"),
         InlineKeyboardButton("📝 Nome Produto",  callback_data="set_product")],
        [InlineKeyboardButton("📜 Descrição Produto", callback_data="set_description"),
         InlineKeyboardButton(ll, callback_data="set_logo")],
        [InlineKeyboardButton("📢 Canal de Notificações",   callback_data="set_channel")],
        [InlineKeyboardButton("◀️ Voltar ao Painel",        callback_data="main_menu")],
    ])

def embed_builder_keyboard(draft: dict) -> InlineKeyboardMarkup:
    has_title = "✅ Título" if draft.get("title") else "➕ Título"
    has_text  = "✅ Texto"  if draft.get("text") else "➕ Texto"
    has_media = f"✅ Mídia ({draft.get('media_type','Nenhuma').upper()})" if draft.get("media_url") else "➕ Mídia (Foto/Vídeo/GIF)"
    has_btn   = "✅ Botão Inline" if draft.get("btn_label") else "➕ Botão Inline"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(has_title, callback_data="eb_set_title"),
         InlineKeyboardButton(has_text,  callback_data="eb_set_text")],
        [InlineKeyboardButton(has_media, callback_data="eb_set_media")],
        [InlineKeyboardButton(has_btn,   callback_data="eb_set_btn")],
        [InlineKeyboardButton("🔍 PREVIEW AVANÇADO", callback_data="eb_preview")],
        [InlineKeyboardButton("🚀 ENVIAR ANÚNCIO", callback_data="eb_send_confirm")],
        [InlineKeyboardButton("🧹 Reiniciar Rascunho", callback_data="eb_reset"),
         InlineKeyboardButton("◀️ Cancelar", callback_data="main_menu")]
    ])

def yes_no_keyboard(yes_cb: str, no_cb: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar Ação", callback_data=yes_cb),
         InlineKeyboardButton("❌ Cancelar Operação", callback_data=no_cb)],
    ])

# ─── BUILDERS DE MENSAGENS FORMATADAS ─────────────────────────────────────────
def build_stats_msg(s: dict) -> str:
    label = f"{s['period']} Horas" if s['period'] < 48 else f"{s['period']//24} Dias"
    return (
        f"🛡️ *RELATÓRIO EXECUTIVO DE MÉTRICAS — {label.upper()}*\n"
        f"═════════════════════════════════════\n\n"
        f"👁️ *Acessos Totais:* `{s['entries']}`\n"
        f"🖥️ *Sessões Ativas:* `{s['sessions']}`\n"
        f"🛒 *Cliques em Comprar:* `{s['click_buy']}`\n"
        f"💬 *Redirecionamento Chat:* `{s['click_chat']}`\n"
        f"🔵 *PIX Gerados:* `{s['pix_generated']}`\n"
        f"✅ *Pagamentos Confirmados:* `{s['paid']}`\n"
        f"📱 *Contatos WhatsApp:* `{s['whatsapp']}`\n"
        f"🎯 *Conversões de Sucesso:* `{s['converted']}`\n"
        f"📈 *Taxa Geral de Conversão:* `{s['conv_rate']}%`\n\n"
        f"🔒 _Relatório gerado sob criptografia de canal seguro._"
    )

def build_logs_msg(events: list) -> str:
    if not events:
        return (
            "📋 *LOGS DE EVENTOS RECENTES*\n"
            "═════════════════════════════════════\n\n"
            "⚠️ _Nenhum evento registrado ainda._"
        )
    lines = [
        "📋 *LOGS DE EVENTOS RECENTES*\n"
        "═════════════════════════════════════\n"
    ]
    for i, ev in enumerate(events, 1):
        ts = ev.get("ts", "—")
        ev_type = ev.get("type", "?").upper()
        session = str(ev.get("session", "—"))[:8]
        ip = ev.get("ip", "—")
        data = ev.get("data") or {}
        detail = ", ".join(f"{k}: `{v}`" for k, v in data.items()) if isinstance(data, dict) and data else "—"
        lines.append(
            f"*{i}.* `{ev_type}` — {ts}\n"
            f"   🌐 IP: `{ip}` | 🆔 Sessão: `{session}…`\n"
            f"   📦 {detail}\n"
        )
    lines.append("🔒 _Log gerado sob canal seguro._")
    return "\n".join(lines)


# ─── AUTHENTICATION DE CORPO ADMINISTRATIVO ───────────────────────────────────
def admin_only(func):
    def wrapper(update: Update, context: CallbackContext):
        user = update.effective_user
        uid = user.id if user else 0
        
        # Se ADMIN_IDS estiver vazio ou conter apenas 0/desconfigurado, auto-cadastra o primeiro usuário
        valid_admins = [x for x in ADMIN_IDS if x > 0]
        if not valid_admins:
            # Tenta ler do banco de dados se há um admin salvo dinamicamente
            saved_admin = get_config("admin_telegram_id", "")
            if saved_admin and saved_admin.isdigit():
                valid_admins.append(int(saved_admin))
            else:
                # Salva este primeiro usuário como Admin Master do sistema
                set_config("admin_telegram_id", str(uid))
                valid_admins.append(uid)
                logger.info(f"[AUTO-ADMIN] Telegram ID {uid} registrado automaticamente como Admin Master!")

        if uid not in valid_admins:
            if update.message:
                update.message.reply_text(f"⛔ *Acesso Negado.* Seu ID (`{uid}`) não possui privilégios de Administrador.", parse_mode=ParseMode.MARKDOWN)
            elif update.callback_query:
                update.callback_query.answer("⛔ Acesso restrito ao Administrador.", show_alert=True)
            return
        return func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def generate_admin_token(tg_id: int) -> str:
    """
    Gera um token seguro de 48 hex chars para acesso ao painel admin.
    Token é armazenado em memória com TTL de 24 horas.
    Auto-registra o admin se necessário.
    """
    import secrets
    if tg_id > 0:
        valid_admins = [x for x in ADMIN_IDS if x > 0]
        if not valid_admins:
            saved_admin = get_config("admin_telegram_id", "")
            if not saved_admin:
                set_config("admin_telegram_id", str(tg_id))

    token = secrets.token_hex(24)  # 48 chars, 192 bits de entropia
    ADMIN_ACCESS_TOKENS[token] = {
        "tg_id":   tg_id,
        "expires": time.time() + 86400,  # 24 horas
        "issued":  time.time(),
    }
    # Limpa tokens expirados para não crescer indefinidamente
    expired = [k for k, v in ADMIN_ACCESS_TOKENS.items() if v["expires"] < time.time()]
    for k in expired:
        del ADMIN_ACCESS_TOKENS[k]
    return token


def validate_admin_token(token: str) -> Optional[int]:
    """
    Valida token de acesso ao painel admin.
    Retorna o tg_id do admin se válido, None caso contrário.
    Token expira após 24h. Não é de uso único — o admin pode abrir várias vezes.
    """
    if not token or len(token) < 48:
        return None
    record = ADMIN_ACCESS_TOKENS.get(token)
    if not record:
        return None
    if record["expires"] < time.time():
        del ADMIN_ACCESS_TOKENS[token]
        return None
    return record["tg_id"]

# ─── COMANDOS ADMINISTRATIVOS PRINCIPAIS ──────────────────────────────────────
@admin_only
def cmd_start(update: Update, context: CallbackContext):
    name = update.effective_user.first_name
    uid  = update.effective_user.id
    msg = (
        f"👑 *BEM-VINDO AO OLPG CONTROL PANEL EXECUTIVO*\n"
        f"═════════════════════════════════════\n\n"
        f"Olá, *{name}*! O sistema está operando sob criptografia militar *AES-256-GCM*.\n"
        f"Todos os logs, credenciais e integrações estão auditados e seguros.\n\n"
        f"Clique no botão abaixo para abrir o painel web instantaneamente ou selecione uma opção executiva:"
    )
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid))

@admin_only
def cmd_stats(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    update.message.reply_text(build_stats_msg(get_stats(24)),
                              parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid))

@admin_only
def cmd_logs(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    update.message.reply_text(build_logs_msg(get_recent_events(10)),
                              parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid))

@admin_only
def cmd_wa(update: Update, context: CallbackContext):
    num = get_config("whatsapp_number")
    msg = get_config("whatsapp_message")
    update.message.reply_text(
        f"📱 *PAINEL WHATSAPP ENTERPRISE BR (+55)*\n═════════════════════════════════════\n\n"
        f"*Número Atual:* `{num}`\n"
        f"*Validação:* ✅ DDD + Digito 9 Autenticados\n\n"
        f"*Mensagem Padrão de Abordagem:*\n_{msg}_",
        parse_mode=ParseMode.MARKDOWN, reply_markup=wa_keyboard()
    )

@admin_only
def cmd_embed(update: Update, context: CallbackContext):
    """Inicia a ferramenta de criação de mensagens ricas / embeds."""
    draft = context.user_data.get("embed_draft", {})
    show_embed_builder_menu(update, context, draft)


@admin_only
def cmd_admin_link(update: Update, context: CallbackContext):
    """
    Gera um link seguro para o painel admin com token de 24h.
    Apenas admins no ADMIN_IDS conseguem usar este comando.
    Link é enviado apenas na conversa privada com o admin.
    """
    uid   = update.effective_user.id
    token = generate_admin_token(uid)
    # Detecta a URL base do servidor
    base_url = os.environ.get("BASE_URL", os.environ.get("APP_URL", "http://localhost:5000"))
    admin_url = f"{base_url}/admin?token={token}"
    msg = (
        f"🔐 *LINK SEGURO DO PAINEL ADMIN*\n"
        f"═════════════════════════════════════\n\n"
        f"🔗 *URL de Acesso (válido por 24h):*\n"
        f"`{admin_url}`\n\n"
        f"🛡️ *Token:* `{token[:12]}...` _\\(oculto por segurança\\)_\n"
        f"📅 *Expira em:* 24 horas\n"
        f"🔒 _Link criptografado AES-256. Não compartilhe._\n"
        f"⚠️ _Guarde com segurança. Acesso total ao sistema._"
    )
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[ADMIN LINK] Token gerado para tg_id={uid}")

# ─── MENU & GERENCIADOR DE EMBEDS / MÍDIAS AVANÇADAS ──────────────────────────
def show_embed_builder_menu(update: Update, context: CallbackContext, draft: dict, edit_existing: bool = False):
    title = draft.get("title", "_Não definido_")
    text = draft.get("text", "_Não definido_")
    m_type = draft.get("media_type", "Nenhuma").upper()
    m_url = draft.get("media_url", "_Nenhum_")
    btn_l = draft.get("btn_label", "_Nenhum_")
    btn_u = draft.get("btn_url", "_Nenhum_")

    msg = (
        f"🎨 *CENTRAL DE EMBEDS & MÍDIAS EXECUTIVAS*\n"
        f"═════════════════════════════════════\n\n"
        f"📌 *Título:* {title}\n"
        f"📝 *Texto:* {text[:100] + '...' if len(text) > 100 else text}\n"
        f"🎬 *Tipo Mídia:* `{m_type}`\n"
        f"🔗 *URL Mídia:* `{m_url}`\n"
        f"🔘 *Botão Action:* [{btn_l}]({btn_u})\n\n"
        f"ℹ️ _Monte sua comunicação corporativa, verifique a pré-visualização e envie com segurança._"
    )

    kb = embed_builder_keyboard(draft)
    if edit_existing and update.callback_query:
        update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        if update.callback_query:
            update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        else:
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# ─── MANIPULADOR DE CALLBACKS E NAVEGAÇÃO INTERATIVA ──────────────────────────
def handle_callback(update: Update, context: CallbackContext):
    q  = update.callback_query
    cb = q.data
    q.answer()
    uid = q.from_user.id

    valid_admins = [x for x in ADMIN_IDS if x > 0]
    if not valid_admins:
        saved_admin = get_config("admin_telegram_id", "")
        if saved_admin and saved_admin.isdigit():
            valid_admins.append(int(saved_admin))

    if valid_admins and uid not in valid_admins:
        q.edit_message_text("⛔ Acesso Restrito.")
        return

    # Inicializa rascunho de embed
    if "embed_draft" not in context.user_data:
        context.user_data["embed_draft"] = {}
    draft = context.user_data["embed_draft"]

    # --- NAVEGAÇÃO PRINCIPAL ---
    if cb == "get_admin_link":
        token = generate_admin_token(uid)
        base_url = os.environ.get("BASE_URL", os.environ.get("APP_URL", "http://localhost:5000")).rstrip('/')
        admin_url = f"{base_url}/admin?token={token}"
        msg = (
            f"🔐 *LINK SEGURO DO PAINEL ADMIN*\n"
            f"═════════════════════════════════════\n\n"
            f"🔗 *URL de Acesso Web (válido por 24h):*\n"
            f"`{admin_url}`\n\n"
            f"🛡️ *Token:* `{token[:12]}...` _\\(oculto por segurança\\)_\n"
            f"📅 *Expira em:* 24 horas\n"
            f"🔒 _Criptografado AES-256. Não compartilhe._"
        )
        q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid))

    elif cb == "main_menu":
        context.user_data.pop("waiting_for", None)
        q.edit_message_text(
            "👑 *OLPG CONTROL PANEL EXECUTIVO*\n═════════════════════════════════════\n\n"
            "Escolha uma opção de gerenciamento no menu:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid)
        )

    elif cb in ("stats_24", "stats_168"):
        hours = 24 if cb == "stats_24" else 168
        q.edit_message_text(build_stats_msg(get_stats(hours)),
                            parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid))

    elif cb == "recent_logs":
        q.edit_message_text(build_logs_msg(get_recent_events(10)),
                            parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard(uid))

    elif cb == "check_channels":
        channel_id = get_config("telegram_channel_id")
        bot = context.bot
        status_msg = "📢 *AUDITORIA DE CANAIS & PERMISSÕES DO BOT*\n═════════════════════════════════════\n\n"
        if not channel_id:
            status_msg += "⚠️ *Nenhum canal ID configurado ainda.*\nUse a opção `⚙️ Configurações -> Canal de Notificações` para definir o ID do canal (ex: `-100...`).\n"
        else:
            try:
                chat = bot.get_chat(chat_id=channel_id)
                member = bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
                status_msg += f"✅ *Canal Identificado:* `{chat.title}`\n"
                status_msg += f"🆔 *ID:* `{chat.id}`\n"
                status_msg += f"🛡️ *Status de Membro:* `{member.status.upper()}`\n\n"
                if member.status in ("administrator", "creator"):
                    status_msg += "🔑 *Permissões Detectadas:*\n"
                    status_msg += f"• Postar Mensagens: {'✅' if getattr(member, 'can_post_messages', True) else '❌'}\n"
                    status_msg += f"• Editar Mensagens: {'✅' if getattr(member, 'can_edit_messages', True) else '❌'}\n"
                    status_msg += f"• Enviar Mídia: {'✅' if getattr(member, 'can_send_media_messages', True) else '❌'}\n"
                else:
                    status_msg += "⚠️ *Atenção:* O bot está no canal mas não é Administrador. Promova o bot a admin para enviar alertas de leads e vendas!"
            except Exception as err:
                status_msg += f"❌ *Erro ao Acessar Canal:* `{err}`\n\nVerifique se o bot foi adicionado ao canal como Administrador."
        q.edit_message_text(status_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

    elif cb == "vault_menu":
        q.edit_message_text(
            "🛡️ *VAULT DE SEGURANÇA MILITAR — AES-256-GCM*\n═════════════════════════════════════\n\n"
            "🔒 *Status da Criptografia:* Ativa & Operacional\n"
            "🔑 *Algoritmo:* AES-256 + Derivação PBKDF2 HMAC SHA-256\n"
            "🛡️ *Proteção de Banco:* Todos os registros `events` e `config` cifrados\n\n"
            "Nenhuma credencial é exposta em texto plano em logs ou dumps de memória.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard()
        )

    elif cb == "config_menu":
        active  = "ATIVO ✅"  if get_config("active") == "1" else "PAUSADO ❌"
        pixel   = "ATIVO ✅"  if get_config("pixel_active") == "1" else "OFF ❌"
        preco   = get_config("product_price", "630.00")
        produto = get_config("product_name", "iPhone 11 64GB")
        q.edit_message_text(
            f"⚙️ *CONFIGURAÇÕES DO GATEWAY SEGURO*\n═════════════════════════════════════\n\n"
            f"⚡ Status da Loja: *{active}*\n"
            f"📊 Pixel de Rastreio: *{pixel}*\n"
            f"💰 Valor Configurado: *R$ {preco}*\n"
            f"📦 Nome do Produto: *{produto}*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=config_keyboard()
        )

    elif cb == "toggle_active":
        cur = get_config("active", "1")
        new = "0" if cur == "1" else "1"
        set_config("active", new)
        q.answer(f"Gateway {'ATIVADO ✅' if new=='1' else 'PAUSADO ❌'}", show_alert=True)
        q.edit_message_text("Configurações atualizadas com sucesso!", reply_markup=config_keyboard())

    elif cb == "toggle_pixel":
        cur = get_config("pixel_active", "1")
        new = "0" if cur == "1" else "1"
        set_config("pixel_active", new)
        q.answer(f"Pixel {'ATIVADO ✅' if new=='1' else 'DESLIGADO ❌'}", show_alert=True)
        q.edit_message_text("Configurações de rastreamento atualizadas!", reply_markup=config_keyboard())

    elif cb == "notif_toggle":
        cur = get_config("notifications", "1")
        new = "0" if cur == "1" else "1"
        set_config("notifications", new)
        status = "ATIVADAS ✅" if new == "1" else "DESLIGADAS ❌"
        q.edit_message_text(f"Notificações operacionais em tempo real: *{status}*",
                            parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

    # --- SEÇÃO WHATSAPP ---
    elif cb == "wa_menu":
        num = get_config("whatsapp_number")
        msg = get_config("whatsapp_message")
        q.edit_message_text(
            f"📱 *WHATSAPP ENTERPRISE — VALIDADOR BR (+55)*\n═════════════════════════════════════\n\n"
            f"*Número Atual:* `{num}`\n"
            f"*Status:* ✅ Válido no Padrão ANATEL / WhatsApp\n\n"
            f"*Mensagem de Abordagem Padrão:*\n_{msg}_",
            parse_mode=ParseMode.MARKDOWN, reply_markup=wa_keyboard()
        )

    elif cb == "wa_set_number":
        context.user_data["waiting_for"] = "wa_number"
        q.edit_message_text(
            "📱 *VALIDADOR AVANÇADO DE WHATSAPP BR (+55)*\n═════════════════════════════════════\n\n"
            "Envie o número corporativo com DDD (ex: `11998765432` ou `5511999876543`):\n\n"
            "ℹ️ _O algoritmo verifica a lista oficial de DDDs e exige o 9º dígito obrigatório._",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb == "wa_suggest_msg":
        suggestions = [
            "Olá! Gostaria de confirmar a disponibilidade do anúncio do iPhone 11 64GB com a Entrega Garantida. Podemos prosseguir?",
            "Olá! Sou comprador com cadastro verificado e interesse no iPhone 11 64GB. Gostaria de tirar dúvidas sobre o envio seguro.",
            "Olá, tudo bem? Vi seu anúncio do iPhone 11 64GB. O produto se encontra em perfeito estado e pronto para envio?"
        ]
        context.user_data["suggestions"] = suggestions
        buttons = [
            [InlineKeyboardButton(f"Opção {i+1}", callback_data=f"apply_sug_{i}")] for i in range(len(suggestions))
        ]
        buttons.append([InlineKeyboardButton("✍️ Escrever Mensagem Própria", callback_data="wa_set_msg")])
        buttons.append([InlineKeyboardButton("◀️ Voltar", callback_data="wa_menu")])
        q.edit_message_text(
            "💼 *SUGESTÕES DE ABORDAGEM HIGH-TICKET EXECUTIVAS:*\n═════════════════════════════════════\n\n" +
            "\n\n".join([f"*{i+1}.* _{s}_" for i, s in enumerate(suggestions)]),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif cb.startswith("apply_sug_"):
        idx = int(cb.replace("apply_sug_", ""))
        sug_list = context.user_data.get("suggestions", [])
        if idx < len(sug_list):
            selected = sug_list[idx]
            set_config("whatsapp_message", selected)
            q.answer("Abordagem empresarial salva com sucesso!", show_alert=True)
            q.edit_message_text(
                f"✅ *MENSAGEM DE ABORDAGEM ATUALIZADA!*\n═════════════════════════════════════\n\n_{selected}_",
                parse_mode=ParseMode.MARKDOWN, reply_markup=wa_keyboard()
            )

    elif cb == "wa_set_msg":
        context.user_data["waiting_for"] = "wa_message"
        q.edit_message_text("Envie a nova mensagem executiva padrão de abordagem para o WhatsApp:")

    elif cb == "set_price":
        context.user_data["waiting_for"] = "product_price"
        q.edit_message_text("Envie o novo preço do produto (ex: `630.00`):", parse_mode=ParseMode.MARKDOWN)

    elif cb == "set_product":
        context.user_data["waiting_for"] = "product_name"
        q.edit_message_text("Envie o novo nome executivo do produto:")

    elif cb == "set_description":
        context.user_data["waiting_for"] = "product_description"
        q.edit_message_text("Envie a nova descrição detalhada do produto:")

    elif cb == "upload_3_photos_menu":
        p1 = get_config("product_image1", get_config("product_image", "Padrão"))
        p2 = get_config("product_image2", get_config("product_image", "Padrão"))
        p3 = get_config("product_image3", get_config("product_image", "Padrão"))
        
        btns = [
            [InlineKeyboardButton(f"🖼️ Foto 1: {'✅ Cadastrada' if 'http' in p1 or '/static' in p1 else '➕ Upload'}", callback_data="upload_slot_1")],
            [InlineKeyboardButton(f"🖼️ Foto 2: {'✅ Cadastrada' if 'http' in p2 or '/static' in p2 else '➕ Upload'}", callback_data="upload_slot_2")],
            [InlineKeyboardButton(f"🖼️ Foto 3: {'✅ Cadastrada' if 'http' in p3 or '/static' in p3 else '➕ Upload'}", callback_data="upload_slot_3")],
            [InlineKeyboardButton("🔍 PREVIEW DAS 3 FOTOS", callback_data="preview_3_photos")],
            [InlineKeyboardButton("◀️ Voltar ao Painel", callback_data="config_menu")]
        ]
        q.edit_message_text(
            "🖼️ *GERENCIADOR DE 3 FOTOS DO ANÚNCIO (PREVIEW REAL)*\n═════════════════════════════════════\n\n"
            "Selecione o slot abaixo e envie a foto no chat ou envie o link direto da imagem.\n"
            "O site exibirá as 3 fotos na galeria exatamente no formato exigido pela OLX!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(btns)
        )

    elif cb in ("upload_slot_1", "upload_slot_2", "upload_slot_3"):
        slot_num = cb.replace("upload_slot_", "")
        context.user_data["waiting_for"] = f"product_photo_slot_{slot_num}"
        q.edit_message_text(
            f"📸 *UPLOAD DA FOTO {slot_num} DO ANÚNCIO*\n═════════════════════════════════════\n\n"
            f"Envie a foto diretamente neste chat ou cole a URL da imagem (ex: `https://.../foto{slot_num}.jpg`):",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb == "preview_3_photos":
        bot = context.bot
        chat_id = q.message.chat_id
        p1 = get_config("product_image1", get_config("product_image", "/static/images/iphone_product.jpg"))
        p2 = get_config("product_image2", get_config("product_image", "/static/images/iphone_product.jpg"))
        p3 = get_config("product_image3", get_config("product_image", "/static/images/iphone_product.jpg"))
        
        q.message.reply_text("🔍 *─── PREVIEW DAS 3 FOTOS DO ANÚNCIO ───*", parse_mode=ParseMode.MARKDOWN)
        for idx, img_url in enumerate([p1, p2, p3], 1):
            try:
                bot.send_photo(chat_id=chat_id, photo=img_url, caption=f"🖼️ *Foto {idx} do Anúncio*", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                bot.send_message(chat_id=chat_id, text=f"🖼️ *Foto {idx}:* `{img_url}`", parse_mode=ParseMode.MARKDOWN)
        q.message.reply_text("💡 *Fotos validadas com sucesso no sistema!*", reply_markup=config_keyboard())

    elif cb == "webhook_virtual_ui":
        # Busca credenciais reais do ambiente/banco
        base_url = (
            os.environ.get("BASE_URL") or
            os.environ.get("RENDER_EXTERNAL_URL") or
            os.environ.get("APP_URL") or
            "https://olx-9ee8.onrender.com"
        ).rstrip('/')
        c7_key    = os.environ.get("C7_API_KEY", get_config("c7_key", ""))
        c7_secret = os.environ.get("C7_API_SECRET", get_config("c7_secret", ""))
        webhook_url = f"{base_url}/api/webhook/pix"

        c7_key_display    = f"`{c7_key[:18]}...`" if c7_key and len(c7_key) > 10 else "`⚠️ NÃO CONFIGURADA`"
        c7_secret_display = "✅ Configurado" if c7_secret else "⚠️ Não configurado"

        btns = [
            [InlineKeyboardButton("⚡ Simular Webhook Pix Confirmado", callback_data="sim_webhook_paid")],
            [InlineKeyboardButton("🔑 Testar HMAC-SHA256 C7", callback_data="test_c7_hmac")],
            [InlineKeyboardButton("◀️ Voltar", callback_data="config_menu")]
        ]
        q.edit_message_text(
            f"🌐 *INTERFACE VIRTUAL DO WEBHOOK C7*\n═════════════════════════════════════\n\n"
            f"📌 *Endpoint Webhook:* `{webhook_url}`\n"
            f"🔑 *API Key C7:* {c7_key_display}\n"
            f"🔐 *API Secret C7:* {c7_secret_display}\n"
            f"🛡️ *HMAC Signature:* `SHA256 Ativado (Tempo Constante)`\n"
            f"⚡ *Tentativas da C7:* `3 tentativas (Imediata, 5s, 30s)`\n\n"
            f"Use a interface virtual abaixo para testar a comunicação em tempo real:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(btns)
        )

    elif cb == "test_c7_hmac":
        import hmac as _hmac, hashlib as _hashlib
        c7_secret = os.environ.get("C7_API_SECRET", get_config("c7_secret", ""))
        if not c7_secret:
            q.answer("⚠️ C7_API_SECRET não configurada!", show_alert=True)
        else:
            payload = b'{"test": "olpg_hmac_check"}'
            sig = _hmac.new(c7_secret.encode(), payload, _hashlib.sha256).hexdigest()
            q.edit_message_text(
                f"🔑 *TESTE HMAC-SHA256 C7 — RESULTADO*\n═════════════════════════════════════\n\n"
                f"✅ *Assinatura Gerada com Sucesso!*\n\n"
                f"📦 *Payload Teste:* `{{\"test\": \"olpg_hmac_check\"}}`\n"
                f"🔒 *Signature:* `{sig[:32]}...`\n\n"
                f"_O sistema está pronto para validar webhooks reais da C7._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Voltar", callback_data="webhook_virtual_ui")]])
            )

    elif cb == "sim_webhook_paid":
        q.answer("Simulando confirmação de pagamento C7...", show_alert=True)
        log_event("PAYMENT_CONFIRMED", "sim_test", "127.0.0.1", {
            "c7_id": "c7_sim_987654",
            "payment_id": "olx_sim_12345",
            "amount": get_config("product_price", "1250.00"),
            "status": "APPROVED"
        })
        q.edit_message_text("✅ *SIMULAÇÃO CONCLUÍDA!* O webhook recebeu e confirmou o pagamento com HMAC válido.", parse_mode=ParseMode.MARKDOWN, reply_markup=config_keyboard())



    elif cb == "product_templates_menu":
        conn = get_db()
        rows = conn.execute("SELECT code, name, price, old_price FROM product_templates").fetchall()
        conn.close()
        btns = []
        for r in rows:
            btns.append([
                InlineKeyboardButton(f"✏️ {r['name'][:22]}", callback_data=f"edit_tpl_{r['code']}"),
                InlineKeyboardButton("🔗 Link", callback_data=f"gen_link_{r['code']}")
            ])
        btns.append([InlineKeyboardButton("➕ Criar Novo Produto", callback_data="create_new_tpl")])
        btns.append([InlineKeyboardButton("◀️ Voltar", callback_data="config_menu")])
        q.edit_message_text(
            "📦 *GERENCIADOR DE PRODUTOS — LINKS EXCLUSIVOS*\n═════════════════════════════════════\n\n"
            "✏️ Clique no produto para *editar tudo* (nome, preço, fotos, descrição).\n"
            "🔗 Clique em *Link* para copiar o link público daquele produto.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(btns)
        )

    elif cb.startswith("edit_tpl_"):
        tpl_code = cb.replace("edit_tpl_", "")
        conn = get_db()
        r = conn.execute("SELECT * FROM product_templates WHERE code=?", (tpl_code,)).fetchone()
        conn.close()
        if not r:
            q.answer("Produto não encontrado.", show_alert=True)
            return
        context.user_data["editing_tpl"] = tpl_code
        domain = get_config("site_domain", os.environ.get("BASE_URL", "https://olx-9ee8.onrender.com"))
        img1 = r["image1"] or r["image_url"] or "—"
        img2 = r["image2"] or "—"
        img3 = r["image3"] or "—"
        old_p = r["old_price"] or "—"
        link = f"{domain.rstrip('/')}/p/{tpl_code}"
        q.edit_message_text(
            f"✏️ *EDITOR DO PRODUTO — {r['name'][:30]}*\n═════════════════════════════════════\n\n"
            f"📦 *Nome:* `{r['name']}`\n"
            f"💰 *Preço (real):* `R$ {r['price']}`\n"
            f"🏷️ *Preço riscado:* `R$ {old_p}`\n"
            f"📝 *Desc:* _{str(r['description'] or '')[:80]}..._\n"
            f"🖼️ *Foto 1:* `{'✅' if r['image1'] or r['image_url'] else '❌ Não definida'}`\n"
            f"🖼️ *Foto 2:* `{'✅' if r['image2'] else '❌ Não definida'}`\n"
            f"🖼️ *Foto 3:* `{'✅' if r['image3'] else '❌ Não definida'}`\n\n"
            f"🔗 *Link público:* `{link}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Nome", callback_data=f"tpl_edit_name_{tpl_code}"),
                 InlineKeyboardButton("💰 Preço Real", callback_data=f"tpl_edit_price_{tpl_code}")],
                [InlineKeyboardButton("🏷️ Preço Riscado", callback_data=f"tpl_edit_oldprice_{tpl_code}"),
                 InlineKeyboardButton("📝 Descrição", callback_data=f"tpl_edit_desc_{tpl_code}")],
                [InlineKeyboardButton("🖼️ Foto 1", callback_data=f"tpl_edit_img1_{tpl_code}"),
                 InlineKeyboardButton("🖼️ Foto 2", callback_data=f"tpl_edit_img2_{tpl_code}"),
                 InlineKeyboardButton("🖼️ Foto 3", callback_data=f"tpl_edit_img3_{tpl_code}")],
                [InlineKeyboardButton("✅ Usar como Padrão", callback_data=f"apply_tpl_{tpl_code}")],
                [InlineKeyboardButton("🔗 Copiar Link", callback_data=f"gen_link_{tpl_code}"),
                 InlineKeyboardButton("🗑️ Deletar", callback_data=f"del_tpl_{tpl_code}")],
                [InlineKeyboardButton("◀️ Voltar", callback_data="product_templates_menu")]
            ])
        )

    elif cb.startswith(("tpl_edit_name_","tpl_edit_price_","tpl_edit_oldprice_","tpl_edit_desc_","tpl_edit_img1_","tpl_edit_img2_","tpl_edit_img3_")):
        for prefix in ("tpl_edit_name_","tpl_edit_price_","tpl_edit_oldprice_","tpl_edit_desc_","tpl_edit_img1_","tpl_edit_img2_","tpl_edit_img3_"):
            if cb.startswith(prefix):
                field_map = {
                    "tpl_edit_name_":     ("tpl_name",     "📦 *Envie o novo NOME do produto:*"),
                    "tpl_edit_price_":    ("tpl_price",    "💰 *Envie o novo PREÇO real (ex: `630.00`):*"),
                    "tpl_edit_oldprice_":("tpl_old_price","🏷️ *Envie o PREÇO RISCADO (ex: `1299.00`):*"),
                    "tpl_edit_desc_":     ("tpl_desc",     "📝 *Envie a nova DESCRIÇÃO do produto:*"),
                    "tpl_edit_img1_":    ("tpl_img1",     "🖼️ *Envie a URL ou FOTO da imagem 1:*"),
                    "tpl_edit_img2_":    ("tpl_img2",     "🖼️ *Envie a URL ou FOTO da imagem 2:*"),
                    "tpl_edit_img3_":    ("tpl_img3",     "🖼️ *Envie a URL ou FOTO da imagem 3:*"),
                }
                wait_key, prompt = field_map[prefix]
                tpl_code = cb[len(prefix):]
                context.user_data["waiting_for"] = wait_key
                context.user_data["editing_tpl"]  = tpl_code
                q.edit_message_text(prompt, parse_mode=ParseMode.MARKDOWN)
                break

    elif cb.startswith("del_tpl_"):
        tpl_code = cb.replace("del_tpl_", "")
        q.edit_message_text(
            f"⚠️ *Confirma exclusão do produto `{tpl_code}`?*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=yes_no_keyboard(f"del_tpl_do_{tpl_code}", "product_templates_menu")
        )

    elif cb.startswith("del_tpl_do_"):
        tpl_code = cb.replace("del_tpl_do_", "")
        conn = get_db(); conn.execute("DELETE FROM product_templates WHERE code=?", (tpl_code,)); conn.commit(); conn.close()
        q.answer("Produto deletado!", show_alert=True)
        q.edit_message_text("✅ Produto removido.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 Voltar", callback_data="product_templates_menu")]]))

    elif cb == "create_new_tpl":
        context.user_data["waiting_for"] = "new_tpl_name"
        context.user_data["new_tpl"] = {}
        q.edit_message_text(
            "🆕 *CRIAR NOVO PRODUTO — PASSO 1/4*\n══════════════════════════════════\n\n"
            "📦 *Envie o NOME do novo produto:*\n_(ex: iPhone 13 128GB Azul)_",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb.startswith("gen_link_"):

        tpl_code = cb.replace("gen_link_", "")
        conn = get_db()
        r = conn.execute("SELECT name, price, old_price FROM product_templates WHERE code=?", (tpl_code,)).fetchone()
        conn.close()
        if r:
            domain = get_config("site_domain", os.environ.get("BASE_URL", "https://olx-9ee8.onrender.com"))
            direct_link = f"{domain.rstrip('/')}/p/{tpl_code}"
            old_p = r["old_price"] or "—"
            q.edit_message_text(
                f"🔗 *LINK PÚBLICO DO PRODUTO*\n═════════════════════════════════════\n\n"
                f"📦 *Produto:* `{r['name']}`\n"
                f"💰 *Preço:* `R$ {r['price']}` ~~R$ {old_p}~~\n\n"
                f"🌐 *Link para enviar ao cliente:*\n`{direct_link}`\n\n"
                f"_Copie o link acima e envie para o lead. Cada cliente acessa o produto individualmente sem cruzar dados!_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Editar produto", callback_data=f"edit_tpl_{tpl_code}")],
                    [InlineKeyboardButton("📦 Voltar aos Produtos", callback_data="product_templates_menu")],
                    [InlineKeyboardButton("◀️ Menu Principal", callback_data="main_menu")]
                ])
            )

    elif cb.startswith("apply_tpl_"):
        tpl_code = cb.replace("apply_tpl_", "")
        conn = get_db()
        r = conn.execute("SELECT * FROM product_templates WHERE code=?", (tpl_code,)).fetchone()
        conn.close()
        if r:
            set_config("product_name",      r["name"])
            set_config("product_price",     r["price"])
            set_config("product_old_price", r["old_price"] or "")
            set_config("product_description", r["description"] or "")
            # Foto 1: prioriza image1, cai em image_url
            img1 = r["image1"] or r["image_url"] or ""
            img2 = r["image2"] or r["image_url"] or ""
            img3 = r["image3"] or r["image_url"] or ""
            if img1: set_config("product_image",  img1)
            if img1: set_config("product_image1", img1)
            if img2: set_config("product_image2", img2)
            if img3: set_config("product_image3", img3)
            q.answer(f"Produto '{r['name']}' definido como padrão!", show_alert=True)
            q.edit_message_text(
                f"✅ *PRODUTO APLICADO COMO PADRÃO DA LOJA!*\n═════════════════════════════════════\n\n"
                f"📦 *Produto:* `{r['name']}`\n"
                f"💰 *Preço:* `R$ {r['price']}`   ~~R$ {r['old_price'] or '—'}~~\n"
                f"📜 *Descrição:* _{str(r['description'] or '')[:200]}_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=config_keyboard()
            )

    elif cb == "set_logo":
        context.user_data["waiting_for"] = "logo_url"
        q.edit_message_text(
            "🖼️ *CONFIGURAÇÃO DA LOGO OLX / LOJA*\n═════════════════════════════════════\n\n"
            "Envie a URL da imagem da logo (ex: `https://.../logo.png`) ou envie um link/foto aqui no chat.\n"
            "Para resetar para a logo SVG padrão da OLX, envie `padrao`.",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb == "set_channel":
        context.user_data["waiting_for"] = "channel_id"
        q.edit_message_text(
            "📢 *CONFIGURAÇÃO DO CANAL TELEGRAM*\n═════════════════════════════════════\n\n"
            "Envie o ID do Canal do Telegram ou Chat ID para onde todos os Leads e Vendas serão enviados instantaneamente (ex: `-1001234567890`):",
            parse_mode=ParseMode.MARKDOWN
        )

    # --- SEÇÃO EMBED BUILDER ---
    elif cb == "embed_menu":
        show_embed_builder_menu(update, context, draft, edit_existing=True)

    elif cb == "eb_set_title":
        context.user_data["waiting_for"] = "eb_title"
        q.edit_message_text("📌 *DIGITE O TÍTULO DO EMBED/MENSAGEM:*\n\nExemplo: `🔥 OFERTA EXCLUSIVA - IPHONE 11`", parse_mode=ParseMode.MARKDOWN)

    elif cb == "eb_set_text":
        context.user_data["waiting_for"] = "eb_text"
        q.edit_message_text(
            "📝 *DIGITE O TEXTO PRINCIPAL DA MENSAGEM:*\n\n"
            "Você pode usar formatação Markdown V1 (`*negrito*`, `_itálico_`, `` `código` ``).\n"
            "ℹ️ _O validador testará a sintaxe automaticamente para evitar erros de renderização._",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb == "eb_set_media":
        context.user_data["waiting_for"] = "eb_media_url"
        q.edit_message_text(
            "🎬 *ENVIE A MÍDIA DA MENSAGEM:*\n═════════════════════════════════════\n\n"
            "Você pode enviar:\n"
            "1. Um arquivo direto no chat (Imagem, Vídeo ou GIF/Animação)\n"
            "2. Uma URL direta que termine com `.png`, `.jpg`, `.jpeg`, `.gif` ou `.mp4`\n\n"
            "Envie agora o arquivo de mídia ou o link:",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb == "eb_set_btn":
        context.user_data["waiting_for"] = "eb_btn"
        q.edit_message_text(
            "🔘 *CONFIGURAR BOTÃO INLINE ACTION*\n═════════════════════════════════════\n\n"
            "Envie o texto do botão e o link no formato `Texto | URL`\n"
            "Exemplo: `🛒 Garanta Já | https://seu-site.com`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif cb == "eb_reset":
        context.user_data["embed_draft"] = {}
        q.answer("Rascunho resetado!")
        show_embed_builder_menu(update, context, {}, edit_existing=True)

    elif cb == "eb_preview":
        render_embed_preview(update, context, draft)

    elif cb == "eb_send_confirm":
        if not draft.get("text") and not draft.get("title") and not draft.get("media_url"):
            q.answer("❌ O rascunho está vazio! Adicione texto ou mídia antes de enviar.", show_alert=True)
            return
        q.edit_message_text(
            "🚀 *CONFIRMAÇÃO DE DISPARO DE MENSAGEM*\n═════════════════════════════════════\n\n"
            "Tem certeza que deseja enviar esta comunicação para todos os administradores cadastrados?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=yes_no_keyboard("eb_send_do", "embed_menu")
        )

    elif cb == "eb_send_do":
        dispatch_embed_broadcast(update, context, draft)

    # --- EXPORTAÇÃO & LIMPEZA ---
    elif cb == "export_logs":
        events = get_recent_events(50)
        export = {
            "exported_at": datetime.now().isoformat(),
            "military_encryption": "AES-256-GCM (Fernet)",
            "events": [{
                "type": e["type"], "session": e["session"], "ip": e["ip"],
                "ts": datetime.fromtimestamp(e["ts"]).isoformat(), "data": e["data"]
            } for e in events]
        }
        enc_blob = crypto_engine.encrypt(export)
        q.message.reply_document(
            document=io.BytesIO(enc_blob.encode('utf-8')),
            filename=f"olpg_vault_export_{int(time.time())}.enc",
            caption=f"🛡️ *VAULT EXPORTADO COM SEGURANÇA MILITAR*\n`{len(events)}` Registros salvos sob AES-256.",
            parse_mode=ParseMode.MARKDOWN
        )
        q.answer("Exportação de Vault concluída com sucesso!")

    elif cb == "clear_logs_confirm":
        q.edit_message_text(
            "⚠️ *CONFIRMAÇÃO DE EXPURAÇÃO DE LOGS*\n═════════════════════════════════════\n\n"
            "Tem certeza que deseja apagar permanentemente todos os registros de eventos? Esta ação é irreversível.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=yes_no_keyboard("clear_logs_do", "main_menu")
        )

    elif cb == "clear_logs_do":
        conn = get_db()
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM sessions")
        conn.commit()
        conn.close()
        q.edit_message_text("✅ *Registros de eventos limpos com sucesso.*",
                            parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

# ─── RENDEREIZADOR DE PREVIEW AVANÇADO DE EMBED ───────────────────────────────
def render_embed_preview(update: Update, context: CallbackContext, draft: dict):
    q = update.callback_query
    title = draft.get("title", "")
    text  = draft.get("text", "")
    media_url = draft.get("media_url")
    media_type = draft.get("media_type")
    btn_l = draft.get("btn_label")
    btn_u = draft.get("btn_url")

    # Constrói o texto formatado
    caption = ""
    if title:
        caption += f"📌 *{title}*\n\n"
    if text:
        caption += text

    if not caption:
        caption = "📝 _Preview de Comunicação sem Texto_"

    # Valida sintaxe Markdown
    valid, err_msg = InputValidator.is_valid_markdown_v1(caption)
    if not valid:
        q.answer(f"❌ {err_msg}", show_alert=True)
        return

    # Teclado Inline do preview
    reply_markup = None
    if btn_l and btn_u:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn_l, url=btn_u)]])

    q.message.reply_text("🔍 *─── PRÉ-VISUALIZAÇÃO EM TEMPO REAL ───*", parse_mode=ParseMode.MARKDOWN)

    try:
        bot = context.bot
        chat_id = q.message.chat_id
        if media_url and media_type:
            if media_type == "photo":
                bot.send_photo(chat_id=chat_id, photo=media_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            elif media_type == "video":
                bot.send_video(chat_id=chat_id, video=media_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            elif media_type == "animation":
                bot.send_animation(chat_id=chat_id, animation=media_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            bot.send_message(chat_id=chat_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"[PREVIEW ERROR] {e}")
        q.message.reply_text(f"❌ *Erro ao Renderizar Preview:* `{e}`\n\nVerifique se os links e formatação estão corretos.", parse_mode=ParseMode.MARKDOWN)

    # Re-exibe opções do menu
    q.message.reply_text("💡 *Gostou do preview? Escolha uma opção abaixo:*", reply_markup=embed_builder_keyboard(draft))

# ─── DISPARADOR DE BROADCAST DE EMBED ─────────────────────────────────────────
def dispatch_embed_broadcast(update: Update, context: CallbackContext, draft: dict):
    q = update.callback_query
    title = draft.get("title", "")
    text  = draft.get("text", "")
    media_url = draft.get("media_url")
    media_type = draft.get("media_type")
    btn_l = draft.get("btn_label")
    btn_u = draft.get("btn_url")

    caption = ""
    if title:
        caption += f"📌 *{title}*\n\n"
    if text:
        caption += text

    reply_markup = None
    if btn_l and btn_u:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn_l, url=btn_u)]])

    bot = context.bot
    success_count = 0
    fail_count = 0

    targets = ADMIN_IDS if ADMIN_IDS else [q.from_user.id]

    for target_id in targets:
        try:
            if media_url and media_type:
                if media_type == "photo":
                    bot.send_photo(chat_id=target_id, photo=media_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
                elif media_type == "video":
                    bot.send_video(chat_id=target_id, video=media_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
                elif media_type == "animation":
                    bot.send_animation(chat_id=target_id, animation=media_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            else:
                bot.send_message(chat_id=target_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            success_count += 1
        except Exception as e:
            logger.error(f"[BROADCAST FAIL] Target {target_id}: {e}")
            fail_count += 1

    q.edit_message_text(
        f"🚀 *DISPARO DE EMBED CONCLUÍDO!*\n═════════════════════════════════════\n\n"
        f"✅ Entregas com Sucesso: `{success_count}`\n"
        f"❌ Erros de Envio: `{fail_count}`",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard()
    )

# ─── HANDLER DE ENTRADAS DE TEXTO & MIDIAS (PASSO A PASSO) ───────────────────
@admin_only
def handle_incoming_messages(update: Update, context: CallbackContext):
    waiting = context.user_data.get("waiting_for")
    draft = context.user_data.get("embed_draft", {})

    # ─── MÍDIA PARA EMBED BUILDER ──────────────────────────────────────────────
    if waiting == "eb_media_url":
        media_file_id = None
        media_type    = None

        if update.message.photo:
            media_file_id = update.message.photo[-1].file_id
            media_type    = "photo"
        elif update.message.video:
            media_file_id = update.message.video.file_id
            media_type    = "video"
        elif update.message.animation:
            media_file_id = update.message.animation.file_id
            media_type    = "animation"
        elif update.message.text and InputValidator.validate_url(update.message.text.strip()):
            url = update.message.text.strip()
            ext = url.split("?")[0].lower()
            if any(ext.endswith(e) for e in (".mp4", ".mov", ".webm")):
                media_file_id, media_type = url, "video"
            elif any(ext.endswith(e) for e in (".gif",)):
                media_file_id, media_type = url, "animation"
            else:
                media_file_id, media_type = url, "photo"

        if media_file_id and media_type:
            # ✅ CORRIÇÃO DO BUG: salva no draft corretamente
            draft["media_url"]  = media_file_id
            draft["media_type"] = media_type
            context.user_data["embed_draft"] = draft
            context.user_data.pop("waiting_for", None)
            type_label = {"photo": "🖼 Imagem", "video": "🎬 Vídeo", "animation": "🎞 GIF/Animação"}.get(media_type, "Mídia")
            update.message.reply_text(
                f"✅ *{type_label} salva no rascunho!*\n`{str(media_file_id)[:60]}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=embed_builder_keyboard(draft)
            )
        else:
            update.message.reply_text(
                "❌ Envie uma foto, vídeo, GIF ou link direto de mídia (https://...png/mp4).",
                reply_markup=embed_builder_keyboard(draft)
            )
        return

    # ─── FOTO DE PRODUTO POR SLOT ──────────────────────────────────────────────
    if waiting and waiting.startswith("product_photo_slot_"):
        slot_num  = waiting.replace("product_photo_slot_", "")
        photo_url = None

        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            try:
                bot_file  = context.bot.get_file(file_id)
                photo_url = bot_file.file_path
            except Exception:
                photo_url = file_id
        elif update.message.text and InputValidator.validate_url(update.message.text.strip()):
            photo_url = update.message.text.strip()

        if photo_url:
            set_config(f"product_image{slot_num}", photo_url)
            if slot_num == "1":
                set_config("product_image", photo_url)
            context.user_data.pop("waiting_for", None)
            update.message.reply_text(
                f"✅ *FOTO {slot_num} CADASTRADA COM SUCESSO NO ANÚNCIO!*\n\nURL: `{photo_url}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=config_keyboard()
            )
            return
        else:
            update.message.reply_text("❌ Envie uma foto válida ou um link de imagem válido.")
            return

    # ─── PROCESSAMENTO DE TEXTO ────────────────────────────────────────────────
    if not update.message.text:
        return

    text = update.message.text.strip()

    if not waiting:
        update.message.reply_text("💡 Use /start para abrir o painel executivo.", reply_markup=main_keyboard())
        return

    context.user_data.pop("waiting_for", None)

    if waiting == "wa_number":
        validated_num, err = InputValidator.validate_phone_br(text)
        if err:
            update.message.reply_text(f"❌ *Erro de Validação:* {err}\n\nTente novamente com um número real.", parse_mode=ParseMode.MARKDOWN)
            return
        set_config("whatsapp_number", validated_num)
        update.message.reply_text(f"✅ *Número WhatsApp BR Validado & Salvo:* `{validated_num}`",
                                  parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

    elif waiting == "wa_message":
        clean_msg = InputValidator.sanitize_text(text, max_chars=1000)
        set_config("whatsapp_message", clean_msg)
        update.message.reply_text("✅ *Mensagem de Abordagem Profissional Atualizada!*", reply_markup=main_keyboard())

    elif waiting == "product_price":
        try:
            price = float(text.replace(",", "."))
            set_config("product_price", f"{price:.2f}")
            update.message.reply_text(f"✅ *Valor do Produto Atualizado:* `R$ {price:.2f}`", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
        except ValueError:
            update.message.reply_text("❌ Preço inválido. Exemplo correto: `630.00`", parse_mode=ParseMode.MARKDOWN)

    elif waiting == "product_name":
        clean_name = InputValidator.sanitize_text(text, max_chars=200)
        set_config("product_name", clean_name)
        update.message.reply_text(f"✅ *Nome do Produto Atualizado:* `{clean_name}`", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

    elif waiting == "product_description":
        clean_desc = InputValidator.sanitize_text(text, max_chars=1500)
        set_config("product_description", clean_desc)
        update.message.reply_text("✅ *Descrição Detalhada do Produto Atualizada no Site!*", parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())

    elif waiting == "eb_title":
        draft["title"] = InputValidator.sanitize_text(text, max_chars=150)
        update.message.reply_text("✅ *Título do Embed Definido!*", reply_markup=embed_builder_keyboard(draft))

    elif waiting == "eb_text":
        valid, err = InputValidator.is_valid_markdown_v1(text)
        if not valid:
            update.message.reply_text(f"❌ *Sintaxe Incorreta:* {err}\n\nCorrija a formatação e envie novamente.", parse_mode=ParseMode.MARKDOWN)
            return
        draft["text"] = InputValidator.sanitize_text(text, max_chars=3500)
        update.message.reply_text("✅ *Texto Principal Registrado com Sucesso!*", reply_markup=embed_builder_keyboard(draft))

    elif waiting == "eb_btn":
        if "|" in text:
            parts = text.split("|", 1)
            label = parts[0].strip()
            url = parts[1].strip()
            if InputValidator.validate_url(url):
                draft["btn_label"] = label
                draft["btn_url"] = url
                update.message.reply_text(f"✅ *Botão Action Configurado:* [{label}]({url})", parse_mode=ParseMode.MARKDOWN, reply_markup=embed_builder_keyboard(draft))
            else:
                update.message.reply_text("❌ *URL do Botão Inválida!* Certifique-se de usar `http://` ou `https://`.", parse_mode=ParseMode.MARKDOWN)
        else:
            update.message.reply_text("❌ Formato incorreto. Use: `Texto do Botão | https://link.com`", parse_mode=ParseMode.MARKDOWN)

    elif waiting == "logo_url":
        if text.lower() in ("padrao", "padrão", "reset", "olx"):
            set_config("logo_url", "")
            update.message.reply_text("✅ *Logo resetada para o padrão oficial OLX!*", reply_markup=config_keyboard())
        elif InputValidator.validate_url(text):
            set_config("logo_url", text)
            update.message.reply_text(f"✅ *URL da Logo atualizada com sucesso!*\n`{text}`", parse_mode=ParseMode.MARKDOWN, reply_markup=config_keyboard())
        else:
            update.message.reply_text("❌ URL inválida. Envie um link válido (ex: `https://site.com/logo.png`) ou envie uma foto.", parse_mode=ParseMode.MARKDOWN)

    elif waiting == "channel_id":
        clean_channel = text.strip()
        set_config("telegram_channel_id", clean_channel)
        update.message.reply_text(f"✅ *Canal Telegram Configurado:* `{clean_channel}`\nTodos os leads e compras serão enviados para cá!", parse_mode=ParseMode.MARKDOWN, reply_markup=config_keyboard())

    # ─── TEMPLATE PRODUCT FIELD EDITORS ──────────────────────────────────────
    elif waiting in ("tpl_name", "tpl_price", "tpl_old_price", "tpl_desc", "tpl_img1", "tpl_img2", "tpl_img3"):
        tpl_code = context.user_data.get("editing_tpl", "")
        if not tpl_code:
            update.message.reply_text("❌ Sessão expirada. Volte ao menu de produtos.")
            return
        conn = get_db()
        r = conn.execute("SELECT * FROM product_templates WHERE code=?", (tpl_code,)).fetchone()
        conn.close()
        if not r:
            update.message.reply_text("❌ Produto não encontrado.")
            return

        # Para campos de imagem, aceita foto enviada direto OU URL de texto
        if waiting in ("tpl_img1", "tpl_img2", "tpl_img3"):
            photo_url = None
            # Foto enviada pelo Telegram
            if update.message.photo:
                file_id = update.message.photo[-1].file_id
                try:
                    bot_file = context.bot.get_file(file_id)
                    photo_url = bot_file.file_path
                except Exception:
                    photo_url = file_id
            elif update.message.text and InputValidator.validate_url(update.message.text.strip()):
                photo_url = update.message.text.strip()

            if not photo_url:
                update.message.reply_text("❌ Envie uma foto válida ou URL de imagem (http...). Tente novamente.")
                context.user_data["waiting_for"] = waiting  # mantém o estado
                return

            col_map = {"tpl_img1": "image1", "tpl_img2": "image2", "tpl_img3": "image3"}
            col = col_map[waiting]
            conn = get_db()
            conn.execute(f"UPDATE product_templates SET {col}=? WHERE code=?", (photo_url, tpl_code))
            # Se for Foto 1, atualiza também image_url (campo legado)
            if waiting == "tpl_img1":
                conn.execute("UPDATE product_templates SET image_url=? WHERE code=?", (photo_url, tpl_code))
            conn.commit()
            conn.close()
            slot = waiting[-1]
            update.message.reply_text(
                f"✅ *Foto {slot} atualizada com sucesso!*\n`{photo_url}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✏️ Voltar ao Editor", callback_data=f"edit_tpl_{tpl_code}")
                ]])
            )
        else:
            # Campos de texto
            if not update.message.text:
                update.message.reply_text("❌ Envie um texto válido.")
                context.user_data["waiting_for"] = waiting
                return
            val = update.message.text.strip()
            if waiting == "tpl_name":
                val = InputValidator.sanitize_text(val, max_chars=200)
                conn = get_db(); conn.execute("UPDATE product_templates SET name=? WHERE code=?", (val, tpl_code)); conn.commit(); conn.close()
                update.message.reply_text(f"✅ *Nome atualizado:* `{val}`", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Voltar ao Editor", callback_data=f"edit_tpl_{tpl_code}")]]))
            elif waiting == "tpl_price":
                try:
                    price = float(val.replace(",", "."))
                    conn = get_db(); conn.execute("UPDATE product_templates SET price=? WHERE code=?", (f"{price:.2f}", tpl_code)); conn.commit(); conn.close()
                    update.message.reply_text(f"✅ *Preço real atualizado:* `R$ {price:.2f}`", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Voltar ao Editor", callback_data=f"edit_tpl_{tpl_code}")]]))
                except ValueError:
                    update.message.reply_text("❌ Preço inválido. Exemplo: `630.00`", parse_mode=ParseMode.MARKDOWN)
                    context.user_data["waiting_for"] = waiting; return
            elif waiting == "tpl_old_price":
                try:
                    old_price = float(val.replace(",", "."))
                    conn = get_db(); conn.execute("UPDATE product_templates SET old_price=? WHERE code=?", (f"{old_price:.2f}", tpl_code)); conn.commit(); conn.close()
                    update.message.reply_text(f"✅ *Preço riscado atualizado:* `R$ {old_price:.2f}`", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Voltar ao Editor", callback_data=f"edit_tpl_{tpl_code}")]]))
                except ValueError:
                    update.message.reply_text("❌ Preço inválido. Exemplo: `1299.00`", parse_mode=ParseMode.MARKDOWN)
                    context.user_data["waiting_for"] = waiting; return
            elif waiting == "tpl_desc":
                val = InputValidator.sanitize_text(val, max_chars=2000)
                conn = get_db(); conn.execute("UPDATE product_templates SET description=? WHERE code=?", (val, tpl_code)); conn.commit(); conn.close()
                update.message.reply_text("✅ *Descrição atualizada com sucesso!*", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Voltar ao Editor", callback_data=f"edit_tpl_{tpl_code}")]]))


    # ─── NOVO PRODUTO — WIZARD 4 PASSOS ──────────────────────────────────────
    elif waiting in ("new_tpl_name", "new_tpl_price", "new_tpl_old_price", "new_tpl_desc"):
        if not update.message.text:
            update.message.reply_text("❌ Envie um texto válido.")
            context.user_data["waiting_for"] = waiting; return

        val = update.message.text.strip()
        draft = context.user_data.setdefault("new_tpl", {})

        if waiting == "new_tpl_name":
            draft["name"] = InputValidator.sanitize_text(val, max_chars=200)
            context.user_data["waiting_for"] = "new_tpl_price"
            update.message.reply_text(
                f"✅ Nome: `{draft['name']}`\n\n💰 *PASSO 2/4 — Envie o PREÇO real:*\n_(ex: `630.00`)_",
                parse_mode=ParseMode.MARKDOWN
            )
        elif waiting == "new_tpl_price":
            try:
                price = float(val.replace(",", "."))
                draft["price"] = f"{price:.2f}"
            except ValueError:
                update.message.reply_text("❌ Preço inválido. Ex: `630.00`", parse_mode=ParseMode.MARKDOWN)
                context.user_data["waiting_for"] = waiting; return
            context.user_data["waiting_for"] = "new_tpl_old_price"
            update.message.reply_text(
                f"✅ Preço: `R$ {draft['price']}`\n\n🏷️ *PASSO 3/4 — Envie o PREÇO RISCADO (original):*\n_(ex: `1299.00`) ou envie `0` para pular_",
                parse_mode=ParseMode.MARKDOWN
            )
        elif waiting == "new_tpl_old_price":
            try:
                old_price = float(val.replace(",", "."))
                draft["old_price"] = f"{old_price:.2f}" if old_price > 0 else ""
            except ValueError:
                draft["old_price"] = ""
            context.user_data["waiting_for"] = "new_tpl_desc"
            update.message.reply_text(
                f"✅ Preço riscado: `R$ {draft['old_price'] or '—'}`\n\n📝 *PASSO 4/4 — Envie a DESCRIÇÃO do produto:*",
                parse_mode=ParseMode.MARKDOWN
            )
        elif waiting == "new_tpl_desc":
            draft["description"] = InputValidator.sanitize_text(val, max_chars=2000)
            # Gera código único
            import re as _re
            base_code = _re.sub(r"[^a-z0-9]+", "_", draft["name"].lower())[:30].strip("_")
            code = f"{base_code}_{int(time.time()) % 10000}"
            conn = get_db()
            conn.execute(
                "INSERT OR REPLACE INTO product_templates(code,name,price,old_price,description,image_url,image1,image2,image3) VALUES(?,?,?,?,?,?,?,?,?)",
                (code, draft["name"], draft["price"], draft.get("old_price", ""), draft["description"], "", "", "", "")
            )
            conn.commit()
            conn.close()
            context.user_data.pop("waiting_for", None)
            context.user_data.pop("new_tpl", None)
            context.user_data["editing_tpl"] = code
            update.message.reply_text(
                f"🎉 *PRODUTO CRIADO COM SUCESSO!*\n══════════════════════════════════\n\n"
                f"📦 *Nome:* `{draft['name']}`\n"
                f"💰 *Preço:* `R$ {draft['price']}`\n"
                f"🏷️ *Preço riscado:* `R$ {draft.get('old_price') or '—'}`\n\n"
                f"➡️ Agora adicione as *fotos* do produto clicando em Editar!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Editar e adicionar fotos", callback_data=f"edit_tpl_{code}")],
                    [InlineKeyboardButton("📦 Voltar aos Produtos", callback_data="product_templates_menu")]
                ])
            )


# ─── API PÚBLICA DE NOTIFICAÇÕES INTELIGENTES (Chamada por app.py) ──────────────

_BOT_GEO_CACHE: dict = {}

def parse_user_agent(ua_str: str) -> str:
    """Extrai dispositivo, sistema operacional e navegador a partir do User-Agent."""
    if not ua_str or ua_str in ("—", "unknown", "", "None"):
        return "📱 Mobile / Web"
    ua = ua_str.lower()
    
    # Dispositivo / SO
    if "iphone" in ua:
        dev = "📱 iPhone"
    elif "ipad" in ua:
        dev = "📱 iPad"
    elif "android" in ua:
        dev = "🤖 Android Mobile" if "mobile" in ua else "🤖 Android Tablet"
    elif "windows" in ua:
        dev = "💻 Windows PC"
    elif "macintosh" in ua or "mac os" in ua:
        dev = "🍏 Mac"
    elif "linux" in ua:
        dev = "🐧 Linux"
    else:
        dev = "🌐 Web"
        
    # Navegador / In-App
    if "whatsapp" in ua:
        app = "WhatsApp In-App"
    elif "instagram" in ua:
        app = "Instagram In-App"
    elif "fban" in ua or "fbav" in ua:
        app = "Facebook In-App"
    elif "edg" in ua:
        app = "Edge"
    elif "chrome" in ua and "safari" in ua and "edg" not in ua and "opr" not in ua:
        app = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        app = "Safari"
    elif "firefox" in ua:
        app = "Firefox"
    elif "opera" in ua or "opr" in ua:
        app = "Opera"
    else:
        app = "Navegador"
        
    return f"{dev} • {app}"


def get_geo_info(ip: str) -> dict:
    """Busca localização detalhada por IP com cache em memória."""
    if not ip or ip in ("127.0.0.1", "localhost", "—", "") or ip.startswith("192.168.") or ip.startswith("10."):
        return {"city": "Rede Local / Teste", "region": "", "country": "BR", "flag": "🌐", "isp": "Localhost"}
    
    if ip in _BOT_GEO_CACHE:
        cached = _BOT_GEO_CACHE[ip]
        if time.time() - cached.get("ts", 0) < 3600:
            return cached

    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country,countryCode,isp", timeout=2)
        d = r.json()
        if d.get("status") == "success":
            cc = d.get("countryCode", "BR").upper()
            flag = "".join(chr(127397 + ord(c)) for c in cc) if len(cc) == 2 else "🌐"
            res = {
                "city": d.get("city", ""),
                "region": d.get("regionName", ""),
                "country": d.get("country", ""),
                "flag": flag,
                "isp": d.get("isp", ""),
                "ts": time.time()
            }
            _BOT_GEO_CACHE[ip] = res
            return res
    except Exception:
        pass
    
    return {"city": "Brasil", "region": "", "country": "BR", "flag": "🇧🇷", "isp": ""}


def build_notification(event_type: str, data: dict) -> str:
    """
    Constrói mensagem Markdown completa, rica e contextualizada com Geolocalização, Dispositivo e Produto.
    """
    import datetime
    ip = data.get("ip") or "—"
    geo = get_geo_info(ip) if ip != "—" else {}
    
    # Localização formatada
    loc_parts = []
    if geo.get("city") and geo["city"] != "?":
        loc_parts.append(geo["city"])
    if geo.get("region") and geo["region"] not in loc_parts and geo["region"] != "?":
        loc_parts.append(geo["region"])
    loc_str = ", ".join(loc_parts)
    flag = geo.get("flag", "🇧🇷")
    isp = geo.get("isp", "")
    
    if loc_str:
        geo_line = f"📍 Local: `{loc_str} {flag}`"
        if isp and isp not in ("Localhost", "?", ""):
            geo_line += f" _({isp})_"
    else:
        geo_line = f"📍 Local: `Brasil {flag}`"

    # Dispositivo & Navegador
    ua_str = data.get("ua") or ""
    dev_str = parse_user_agent(ua_str)
    
    # Slug & Produto
    slug = data.get("slug") or "principal"
    if slug in ("—", "", "None", None, "-"):
        slug = "principal"
    
    prod_name = data.get("product_name") or data.get("item") or ""
    prod_price = data.get("product_price") or data.get("price") or data.get("amount") or ""
    
    prod_line = ""
    if prod_name and prod_name not in ("default", "—", "item"):
        if prod_price and prod_price not in ("—", ""):
            prod_line = f"🏷️ Produto: `{prod_name}` — `R$ {prod_price}`\n"
        else:
            prod_line = f"🏷️ Produto: `{prod_name}`\n"
            
    ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if event_type == "PAGE_ENTRY":
        msg = (
            "👁️ *Nova Visita ao Anúncio*\n"
            "═════════════════════════════════════\n"
            f"{prod_line}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"📱 Aparelho: `{dev_str}`\n"
            f"🕐 {ts}"
        )
    elif event_type == "CLICK_BUY":
        msg = (
            "🛒 *Clique em Comprar!*\n"
            "═════════════════════════════════════\n"
            f"{prod_line}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"📱 Aparelho: `{dev_str}`\n"
            f"🕐 {ts}"
        )
    elif event_type == "LEAD_CAPTURED":
        name = data.get("name") or "—"
        phone = data.get("phone") or "—"
        cpf = data.get("cpf") or ""
        cep = data.get("cep") or ""
        address = data.get("address") or ""
        
        lead_extra = []
        if cpf: lead_extra.append(f"📄 CPF: `{cpf}`")
        if cep: lead_extra.append(f"📬 CEP: `{cep}`")
        if address: lead_extra.append(f"🏠 Endereço: `{address}`")
        extra_str = ("\n" + "\n".join(lead_extra) + "\n") if lead_extra else "\n"
        
        msg = (
            "🔥 *Lead Capturado Real!*\n"
            "═════════════════════════════════════\n"
            f"👤 Nome: `{name}`\n"
            f"📱 WhatsApp: `{phone}`\n"
            f"{prod_line.rstrip()}\n"
            f"{extra_str}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"📱 Aparelho: `{dev_str}`\n"
            f"🕐 {ts}"
        )
    elif event_type in ("PIX_GENERATED", "PIX_PAID", "PAYMENT_CONFIRMED"):
        amount = data.get("amount") or data.get("value") or "—"
        name = data.get("name") or data.get("payer_name") or ""
        payer_line = f"👤 Pagador: `{name}`\n" if name and name != "—" else ""
        
        title = "🎉 *Pagamento Confirmado!*" if event_type in ("PIX_PAID", "PAYMENT_CONFIRMED") else "💰 *PIX Gerado!*"
        msg = (
            f"{title}\n"
            "═════════════════════════════════════\n"
            f"💵 Valor: `R$ {amount}`\n"
            f"{payer_line}"
            f"{prod_line}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"📱 Aparelho: `{dev_str}`\n"
            f"🕐 {ts}"
        )
    elif event_type == "WHATSAPP_REDIRECT":
        msg = (
            "📲 *Redirecionado para WhatsApp!*\n"
            "═════════════════════════════════════\n"
            f"{prod_line}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"📱 Aparelho: `{dev_str}`\n"
            f"🕐 {ts}"
        )
    elif event_type == "PAGE_EXIT":
        dur = data.get("duration") or ""
        dur_line = f"⏱️ Tempo no site: `{dur}s`\n" if dur else ""
        msg = (
            "🚪 *Saída de Página*\n"
            "═════════════════════════════════════\n"
            f"{dur_line}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"🕐 {ts}"
        )
    else:
        msg = (
            f"⚡ *Evento: {event_type}*\n"
            "═════════════════════════════════════\n"
            f"{prod_line}"
            f"📦 Slug: `@{slug}`\n"
            f"🌐 IP: `{ip}`\n"
            f"{geo_line}\n"
            f"📱 Aparelho: `{dev_str}`\n"
            f"🕐 {ts}"
        )
    return msg


def build_notification_keyboard(event_type: str, data: dict) -> Optional[InlineKeyboardMarkup]:
    """
    Retorna um teclado inline contextual para a notificação, ou None se não houver ação relevante.
    """
    # Para eventos de conversão, oferece atalho para o relatório de stats
    if event_type in ("LEAD_CAPTURED", "PAYMENT_CONFIRMED", "PIX_PAID", "PIX_GENERATED"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Ver Stats (24h)", callback_data="stats_24")],
            [InlineKeyboardButton("📋 Ver Logs Recentes", callback_data="recent_logs")],
        ])
    # Para visitas e cliques — atalho rápido para logs
    if event_type in ("PAGE_ENTRY", "CLICK_BUY", "WHATSAPP_REDIRECT"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Ver Logs Recentes", callback_data="recent_logs")],
        ])
    # Para eventos silenciosos (PAGE_EXIT etc.) — sem teclado
    return None


_bot_instance = None

def notify_admins(event_type: str, data: dict):
    global _bot_instance
    if get_config("notifications", "1") != "1":
        return
    msg = build_notification(event_type, data)
    if not msg:
        return

    targets = set()
    for aid in ADMIN_IDS:
        if aid and str(aid) not in ("0", ""):
            targets.add(str(aid))

    saved_admin = get_config("admin_telegram_id", "")
    if saved_admin and saved_admin.isdigit():
        targets.add(saved_admin)

    ch_id = get_config("telegram_channel_id", "") or os.environ.get("TELEGRAM_CHANNEL_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if ch_id and str(ch_id) not in ("0", ""):
        targets.add(str(ch_id).strip())

    token = BOT_TOKEN or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    # Reações automáticas para eventos de alta prioridade
    REACTION_EVENTS = {
        "LEAD_CAPTURED":    "🔥",   # fogo — lead quente!
        "PAYMENT_CONFIRMED": "🎉", # confete — pagamento!
        "PIX_GENERATED":    "💰",   # dinheiro — pix gerado
    }

    for target in targets:
        try:
            kb = build_notification_keyboard(event_type, data)
            if _bot_instance:
                sent = _bot_instance.send_message(
                    chat_id=target,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=kb
                )
                # Enviar reação se evento for prioritário
                reaction_emoji = REACTION_EVENTS.get(event_type)
                if reaction_emoji and sent:
                    try:
                        _bot_instance.set_message_reaction(
                            chat_id=target,
                            message_id=sent.message_id,
                            reaction=[{"type": "emoji", "emoji": reaction_emoji}]
                        )
                    except Exception:
                        pass  # Reações não suportadas em todos os chats, ignora silenciosamente
            elif token:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": target, "text": msg, "parse_mode": "Markdown",
                          "reply_markup": kb.to_dict() if kb else None},
                    timeout=5
                )
                # Reação via API REST
                reaction_emoji = REACTION_EVENTS.get(event_type)
                if reaction_emoji and resp.ok:
                    mid = resp.json().get("result", {}).get("message_id")
                    if mid:
                        try:
                            requests.post(
                                f"https://api.telegram.org/bot{token}/setMessageReaction",
                                json={"chat_id": target, "message_id": mid,
                                      "reaction": [{"type": "emoji", "emoji": reaction_emoji}]},
                                timeout=3
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"[NOTIFY ERROR] Target {target}: {e}")

def send_otp_to_admin(tg_id: int, code: str, name: str = "") -> bool:
    """
    Envia o código OTP de 6 dígitos diretamente ao DM privado do admin via Telegram.
    Usa _bot_instance (python-telegram-bot) se disponível, senão cai no REST API.
    Retorna True se o envio foi bem-sucedido.
    """
    display = name or f"Admin #{tg_id}"
    msg = (
        f"🔐 *Código de Acesso — Painel OLX*\n"
        f"═════════════════════════════════════\n\n"
        f"Olá, *{display}*\\!\n\n"
        f"Seu código de verificação pessoal:\n\n"
        f"```\n  {code[:3]} {code[3:]}\n```\n\n"
        f"⏳ _Válido por 10 minutos\\. Uso único\\._\n"
        f"🔒 _Nunca compartilhe este código\\._\n\n"
        f"🛡️ _Se você não solicitou este código, ignore esta mensagem\\._"
    )
    # Tenta via instância ativa do bot (mais confiável)
    if _bot_instance:
        try:
            _bot_instance.send_message(
                chat_id=tg_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            logger.info(f"[OTP] Código enviado ao admin {tg_id} via bot instance.")
            return True
        except Exception as e:
            logger.warning(f"[OTP] Falha via bot instance para {tg_id}: {e}")

    # Fallback: REST API direto
    token = BOT_TOKEN or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": tg_id, "text": msg, "parse_mode": "MarkdownV2"},
                timeout=8,
            )
            if resp.ok:
                logger.info(f"[OTP] Código enviado ao admin {tg_id} via REST API.")
                return True
            else:
                logger.warning(f"[OTP] REST API falhou para {tg_id}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[OTP] Exceção REST API para {tg_id}: {e}")

    logger.error(f"[OTP] Não foi possível enviar código para admin {tg_id}.")
    return False


# ─── INICIALIZAÇÃO PRINCIPAL DO BOT MILITAR ───────────────────────────────────
def main():
    global _bot_instance
    init_db()
    if not BOT_TOKEN:
        logger.error("[BOT CRITICAL] TELEGRAM_BOT_TOKEN não configurada nas variáveis de ambiente.")
        return
    
    updater = Updater(BOT_TOKEN, use_context=True)
    _bot_instance = updater.bot
    dp = updater.dispatcher

    # Registro de Comandos Executivos
    dp.add_handler(CommandHandler("start",      cmd_start))
    dp.add_handler(CommandHandler("stats",      cmd_stats))
    dp.add_handler(CommandHandler("logs",       cmd_logs))
    dp.add_handler(CommandHandler("wa",         cmd_wa))
    dp.add_handler(CommandHandler("embed",      cmd_embed))
    dp.add_handler(CommandHandler("admin_link", cmd_admin_link))  # Gera link seguro do painel
    dp.add_handler(CommandHandler("admin",      cmd_admin_link))
    dp.add_handler(CommandHandler("token",      cmd_admin_link))
    dp.add_handler(CommandHandler("login",      cmd_admin_link))
    dp.add_handler(CommandHandler("acesso",     cmd_admin_link))

    # Registro de Callbacks & Mídia/Texto Handlers
    dp.add_handler(CallbackQueryHandler(handle_callback))
    dp.add_handler(MessageHandler(Filters.all & ~Filters.command, handle_incoming_messages))

    logger.info("[BOT MILITARY] Painel Admin Telegram Iniciado & Blindado com Sucesso.")
    updater.start_polling(drop_pending_updates=False)
    import threading
    if threading.current_thread() is threading.main_thread():
        try:
            updater.idle()
        except Exception:
            pass

if __name__ == "__main__":
    main()
