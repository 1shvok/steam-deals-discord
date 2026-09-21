import json
import os
import requests

API_KEY = os.environ["ITAD_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

ITAD_URL = "https://api.isthereanydeal.com/deals/v2"
HISTORY_FILE = "sent_deals.json"

params = {
    "country": "PT",
    "shops": "61",
    "limit": 50,
    "sort": "-cut",
    "filter": '{"cut":{"min":50}}'
}

headers = {
    "ITAD-API-Key": API_KEY
}


# -------------------------
# Load sent deals
# -------------------------

try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        sent_deals = set(json.load(file))
except FileNotFoundError:
    sent_deals = set()


print(f"Previously sent deals: {len(sent_deals)}")


# -------------------------
# Get deals from ITAD
# -------------------------

response = requests.get(
    ITAD_URL,
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


# -------------------------
# Filter games only
# -------------------------

games = []

for deal in deals:
    if deal.get("type") != "game":
        continue

    deal_info = deal["deal"]

    price = deal_info["price"]["amount"]
    discount = deal_info["cut"]

    # Unique notification ID.
    # Same game + same price + same discount = same notification.
    deal_key = f'{deal["id"]}:{price}:{discount}'

    if deal_key in sent_deals:
        continue

    games.append((deal, deal_key))


print(f"New game deals: {len(games)}")


# -------------------------
# Send deals to Discord
# -------------------------

sent_now = 0

for deal, deal_key in games:

    title = deal["title"]
    deal_info = deal["deal"]

    price = deal_info["price"]["amount"]
    regular_price = deal_info["regular"]["amount"]
    discount = deal_info["cut"]
    currency = deal_info["price"]["currency"]
    url = deal_info["url"]

    embed = {
        "title": f"{discount}% OFF — {title}",
        "description": (
            f"~~{regular_price:.2f} {currency}~~ → "
            f"**{price:.2f} {currency}**"
        ),
        "url": url,
        "color": 5763719,
        "footer": {
            "text": "Steam deal • IsThereAnyDeal"
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

    if discord_response.status_code not in (200, 204):
        print(f"Discord error for {title}:")
        print(discord_response.text)
        raise SystemExit(1)

    print(
        f"Sent: {title} | "
        f"{discount}% OFF | "
        f"{regular_price:.2f} {currency} -> "
        f"{price:.2f} {currency}"
    )

    sent_deals.add(deal_key)
    sent_now += 1


# -------------------------
# Save history
# -------------------------

with open(HISTORY_FILE, "w", encoding="utf-8") as file:
    json.dump(
        sorted(sent_deals),
        file,
        indent=2,
        ensure_ascii=False
    )

print()
print(f"Sent this run: {sent_now}")
print(f"Total saved deals: {len(sent_deals)}")
