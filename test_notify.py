import requests

requests.post(
    "https://ntfy.sh/AutomWazeNozaySafran_notification",
    data="Hello depuis Python !"
)

print("Notification envoyée")