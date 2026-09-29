import os
import threading
import time

def start_services():
    # Inicia bot em thread paralela se o bot.py estiver presente
    try:
        import bot
        bot.init_db()
        updater = bot.main_bot_thread() if hasattr(bot, 'main_bot_thread') else None
    except Exception as e:
        print(f"[Worker] Erro ao iniciar bot: {e}")

if __name__ == "__main__":
    from app import app
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
