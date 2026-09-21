import os
import requests

API_KEY = os.environ["ITAD_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

URL = "https://api.isthereanydeal.com/deals/v2"

params = {
    "country": "PT",
    "shops": "61",
    "limit": 10,
    "sort": "-cut",
    "filter": '{"cut":{"min":50}}'
}

headers = {
    "ITAD-API-Key": API_KEY
}

response = requests.get(
    URL,
    params=params,
    headers=headers,
    timeout=30
)

print("ITAD Status:", response.status_code)

if response.status_code != 200:
    print(response.text)
    raise SystemExit(1)

data = response.json()
deals = data.get("list", [])

print(f"Deals received: {len(deals)}")

if not deals:
    print("No deals found.")
    raise SystemExit(0)

# Берём только первую скидку
deal = deals[0]

title = deal["title"]
deal_info = deal["deal"]

price = deal_info["price"]["amount"]
regular_price = deal_info["regular"]["amount"]
discount = deal_info["cut"]
currency = deal_info["price"]["currency"]
url = deal_info["url"]

print()
print(f"Sending to Discord:")
print(f"{title} | {discount}% OFF | {regular_price:.2f} {currency} -> {price:.2f} {currency}")

# Discord Embed
embed = {
    "title": f"{discount}% OFF — {title}",
    "description": (
        f"~~{regular_price:.2f} {currency}~~ → "
        f"**{price:.2f} {currency}**"
    ),
    "url": url,
    "color": 5763719,
    "footer": {
        "text": "Steam deal • Powered by IsThereAnyDeal"
    }
}

payload = {
    "embeds": [embed]
}

discord_response = requests.post(
    DISCORD_WEBHOOK_URL,
    json=payload,
    timeout=30
)

print("Discord Status:", discord_response.status_code)

if discord_response.status_code not in (200, 204):
    print(discord_response.text)
    raise SystemExit(1)

print("Deal sent successfully!")
