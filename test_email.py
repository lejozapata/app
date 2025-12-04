import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.getenv("SARA_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SARA_SMTP_PORT", "587"))
SMTP_USER = os.getenv("SARA_SMTP_USER")
SMTP_PASSWORD = os.getenv("SARA_SMTP_PASSWORD")

print("HOST:", SMTP_HOST)
print("PORT:", SMTP_PORT)
print("USER:", SMTP_USER)

msg = EmailMessage()
msg["Subject"] = "Prueba Sara Psicóloga"
msg["From"] = SMTP_USER
msg["To"] = SMTP_USER  # te lo envías a ti mismo para probar
msg.set_content("Este es un correo de prueba desde la app de Sara.")

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
    smtp.starttls()
    smtp.login(SMTP_USER, SMTP_PASSWORD)
    smtp.send_message(msg)

print("Correo enviado OK")
