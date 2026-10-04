import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os

# Credenciais seguras puxadas das Variáveis de Ambiente do Render
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "olxvendaconfirmadasbrasil@gmail.com")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")

def send_confirmation_email(to_email: str, subject: str = "Confirmação de Compra - OLX Pay", html_content: str = None):
    """
    Dispara um email personalizado usando os servidores oficiais do Gmail.
    """
    if not html_content:
        # Template padrão de fallback
        html_content = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eaeaea; border-radius: 10px;">
            <h2 style="color: #6d28d9;">Pagamento Confirmado!</h2>
            <p>Olá! Obrigado por comprar com a <strong>OLX Pay Seguro</strong>.</p>
            <p>Seu pagamento foi aprovado com sucesso e o vendedor já foi notificado para realizar o envio.</p>
            <br>
            <p>Qualquer dúvida, entre em contato conosco.</p>
        </div>
        """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    
    # O Nome que aparece na caixa de entrada do cliente:
    msg['From'] = f"OLX Pay Seguro <{GMAIL_SENDER}>"
    msg['To'] = to_email

    # Anexa o HTML
    part = MIMEText(html_content, 'html')
    msg.attach(part)

    try:
        # Conecta ao servidor do Google
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=5)
        server.starttls() # Inicia a criptografia TLS
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        
        # Envia a mensagem
        server.sendmail(GMAIL_SENDER, to_email, msg.as_string())
        server.quit()
        
        print(f"[OK] Email enviado com sucesso via Gmail para {to_email}.")
        return True
    except Exception as e:
        print(f"[ERRO] Erro ao enviar email via Gmail: {e}")
        return False

if __name__ == "__main__":
    # Teste rápido
    print("Testando disparo de email via Gmail...")
    send_confirmation_email(
        to_email="bladestudiosltda@gmail.com", 
        subject="Hello World - Teste Gmail",
        html_content="<p>Congrats on sending your <strong>first email</strong> com Python e Gmail SMTP!</p>"
    )
