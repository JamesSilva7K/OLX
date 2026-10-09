import os
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "olxvendaconfirmadasbrasil@gmail.com")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
GOOGLE_SCRIPT_URL = os.environ.get("GOOGLE_SCRIPT_URL", "").strip()

def obfuscate_text(html: str) -> str:
    # Removido obfuscação com &#8203; pois os filtros modernos marcam como SPAM automaticamente.
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
    # Usa 'related' para embutir imagens e 'alternative' para texto puro e HTML
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = f"OLX Pay Seguro <{GMAIL_SENDER}>"
    msg['To'] = to_email
    
    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)

    import re
    import os
    from email.mime.image import MIMEImage

    # Remove HTML tags to create a plain text version
    plain_text = re.sub('<[^<]+?>', '', html_content).replace('&#8203;', '')
    msg_alt.attach(MIMEText(plain_text, 'plain'))

    # Padrão para achar imagens em static/email_images
    image_pattern = r'src=["\']([^"\']*?static/email_images/([^"\']+))["\']'
    
    # Função para trocar URL por cid:
    def replace_image(match):
        filename = match.group(2)
        return f'src="cid:{filename}"'

    new_html = re.sub(image_pattern, replace_image, html_content)
    msg_alt.attach(MIMEText(new_html, 'html'))

    # Anexa as imagens encontradas no email
    for match in re.finditer(image_pattern, html_content):
        filename = match.group(2)
        filepath = os.path.join(os.path.dirname(__file__), 'static', 'email_images', filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    img_data = f.read()
                img = MIMEImage(img_data)
                img.add_header('Content-ID', f'<{filename}>')
                img.add_header('Content-Disposition', 'inline', filename=filename)
                msg.attach(img)
            except Exception as e:
                print(f"[ERRO] Falha ao anexar imagem {filename}: {e}")

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
