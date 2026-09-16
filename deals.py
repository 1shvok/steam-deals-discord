import os
import requests

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

API_URL = "https://www.cheapshark.com/api/1.0/deals"

headers = {
    "User-Agent": "SteamDealsDiscordBot/1.0"
}

params = {
    "storeID": "1",
    "onSale": "1",
    "pageSize": "1",
    "sortBy": "Savings",
    "desc": "1"
}

response = requests.get(
    API_URL,
    params=params,
    headers=headers,
    timeout=30
)

if response.status_code != 200:
    print(f"CheapShark error: {response.status_code}")
    print(response.text)
    raise SystemExit(1)

deals = response.json()

if not deals:
    print("No Steam deals found.")
    raise SystemExit(0)

deal = deals[0]

title = deal["title"]
sale_price = deal["salePrice"]
normal_price = deal["normalPrice"]
savings = float(deal["savings"])
deal_id = deal["dealID"]

deal_url = f"https://www.cheapshark.com/redirect?dealID={deal_id}"

embed = {
    "title": f"🔥 {title}",
    "url": deal_url,
    "description": (
        f"**{savings:.0f}% OFF**\n\n"
        f"~~${normal_price}~~ → **${sale_price}**"
    ),
    "fields": [
        {
            "name": "Store",
            "value": "Steam",
            "inline": True
        },
        {
            "name": "Discount",
            "value": f"{savings:.0f}%",
            "inline": True
        }
    ],
    "footer": {
        "text": "Powered by CheapShark"
    }
}

data = {
    "username": "Steam Deals",
    "embeds": [embed]
}

discord_response = requests.post(
    WEBHOOK_URL,
    json=data,
    timeout=30
)

if discord_response.status_code == 204:
    print(f"Deal sent successfully: {title}")
else:
    print(f"Discord error: {discord_response.status_code}")
    print(discord_response.text)
    raise SystemExit(1)
