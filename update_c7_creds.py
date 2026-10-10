"""
Script para atualizar as credenciais C7 no vault do OLPG.
Executa uma vez e pode ser deletado depois.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

# Script usado para atualizar credenciais C7 no vault (já executado, pode ser deletado)
# Credenciais removidas por segurança antes do commit.
NEW_API_KEY    = ""
NEW_API_SECRET = ""

import sqlite3
from vault import save_gateway_credentials, get_gateway_credentials, _decrypt

DB_PATH = os.environ.get("DB_PATH", "olpg_logs.db")

def get_config(key):
    """Lê config criptografado do banco."""
    try:
        import sqlite3 as _sq
        from cryptography.fernet import Fernet
        master = os.environ.get(
            "VAULT_MASTER_KEY",
            os.environ.get("FERNET_KEY", os.environ.get("SECRET_KEY", "OLPG_VAULT_MASTER_2026_BLADE_SECURE"))
        ).encode()
        with _sq.connect(DB_PATH) as c:
            row = c.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        from cryptography.fernet import Fernet as F
        import base64, hashlib
        # Tenta Fernet direto com a chave master derivada
        try:
            key_b64 = base64.urlsafe_b64encode(hashlib.sha256(master).digest())
            f = F(key_b64)
            return f.decrypt(row[0].encode()).decode()
        except Exception:
            return None
    except Exception as e:
        print(f"[WARN] Não foi possível descriptografar config: {e}")
        return None

def main():
    # Tenta pegar admin_id da config
    admin_id_str = get_config("admin_telegram_id")
    
    # Admin ID fixado diretamente
    admin_id = 8932547795
    print(f"[INFO] Usando admin_id={admin_id}")
    
    # Salva as novas credenciais no vault
    print(f"\n[INFO] Salvando credenciais C7 para admin_id={admin_id}...")
    
    fields = {
        "api_key":    NEW_API_KEY,
        "api_secret": NEW_API_SECRET,
    }
    
    ok = save_gateway_credentials(admin_id, "c7", fields, ip="script")
    
    if ok:
        print("[OK] Credenciais salvas com sucesso no vault!")
        # Verifica
        creds = get_gateway_credentials(admin_id, "c7")
        key_preview = creds.get("api_key", "")[:20] + "..."
        sec_preview = creds.get("api_secret", "")[:10] + "..."
        print(f"[VERIFY] api_key    = {key_preview}")
        print(f"[VERIFY] api_secret = {sec_preview}")
        print("\n✅ Feito! Reinicie o servidor para aplicar.")
    else:
        print("[ERRO] Falha ao salvar credenciais. Verifique o vault.py.")

if __name__ == "__main__":
    main()
