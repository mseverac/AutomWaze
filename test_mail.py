import smtplib
from email.mime.text import MIMEText

# Informations du mail
expediteur = "mdddmat@gmail.com"
mot_de_passe = "Mathije2003!"
destinataire = "mathijs.svrc@gmail.com"

# Création du message
message = MIMEText("Bonjour,\n\nCeci est un e-mail envoyé depuis Python.")
message["Subject"] = "Test Python"
message["From"] = expediteur
message["To"] = destinataire

# Connexion au serveur SMTP de Gmail
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
        serveur.login(expediteur, mot_de_passe)
        serveur.send_message(message)
except Exception as e:
    print(type(e).__name__)
    print(e)