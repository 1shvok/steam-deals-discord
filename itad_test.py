import json
import os
import time
import requests

API_KEY = os.environ["ITAD_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

ITAD_URL = "https://api.isthereanydeal.com/deals/v2"

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

    games.append(deal)

print(f"Game deals: {len(games)}")


# -------------------------
# Create Discord embeds
# -------------------------

embeds = []

for deal in games:

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

    embeds.append(embed)


# -------------------------
# Send embeds in batches
# -------------------------

BATCH_SIZE = 10

total_batches = (len(embeds) + BATCH_SIZE - 1) // BATCH_SIZE

print(f"Discord batches: {total_batches}")

for batch_number, start in enumerate(
    range(0, len(embeds), BATCH_SIZE),
    start=1
):

    batch = embeds[start:start + BATCH_SIZE]

    payload = {
        "embeds": batch
    }

    while True:

        discord_response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=30
        )

        if discord_response.status_code in (200, 204):
            print(
                f"Batch {batch_number}/{total_batches} "
                f"sent successfully ({len(batch)} deals)."
            )
            break

        if discord_response.status_code == 429:

            try:
                retry_data = discord_response.json()
                retry_after = float(
                    retry_data.get("retry_after", 1)
                )
            except Exception:
                retry_after = 1

            print(
                f"Discord rate limit. "
                f"Waiting {retry_after} seconds..."
            )

            time.sleep(retry_after + 0.2)

            continue

        print("Discord error:")
        print(discord_response.text)
        raise SystemExit(1)

    # Small pause between batches
    time.sleep(1)


print()
print("All deals sent successfully!")
