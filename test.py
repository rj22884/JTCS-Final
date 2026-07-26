import smtplib
from email.mime.text import MIMEText

# GoDaddy Professional Email (Titan)
SMTP_SERVER = "smtpout.secureserver.net"
SMTP_PORT = 465

EMAIL = "admin@jtcsxpert.com"
PASSWORD = "Kjss@802576"  # Replace with your mailbox password

TO_EMAIL = "lparth777@gmail.com"

msg = MIMEText(
    "Hello,\n\nThis is a test email sent from JTCS ERP using GoDaddy Professional Email.\n\nRegards,\nJTCS ERP"
)

msg["Subject"] = "JTCS ERP Test Email"
msg["From"] = EMAIL
msg["To"] = TO_EMAIL

try:
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(EMAIL, PASSWORD)
        server.send_message(msg)

    print("✅ Email sent successfully!")

except Exception as e:
    print("❌ Failed to send email:")
    print(e)