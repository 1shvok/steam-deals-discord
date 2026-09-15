import os
import requests

webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

data = {
    "username": "Steam Deals",
    "content": "🎮 **Steam Deals Bot**\n\nТестовое сообщение успешно отправлено! 🚀"
}

response = requests.post(webhook_url, json=data)

if response.status_code == 204:
    print("Сообщение успешно отправлено в Discord!")
else:
    print(f"Ошибка Discord: {response.status_code}")
    print(response.text)
