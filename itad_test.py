import json
import os
import time
import requests

API_KEY = os.environ["ITAD_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

ITAD_URL = "https://api.isthereanydeal.com/deals/v2"
HISTORY_FILE = "sent_deals.json"


# -------------------------
# Load sent deals history
# -------------------------

try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        history = json.load(file)

    if not isinstance(history, dict):
        history = {}

except (FileNotFoundError, json.JSONDecodeError):
    history = {}

print(f"Previously sent deals: {len(history)}")


# -------------------------
# Get deals from ITAD
# -------------------------

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
# Find new or changed deals
# -------------------------

new_deals = []

for deal in games:

    deal_id = str(deal["id"])
    deal_info = deal["deal"]

    current_state = {
        "title": deal["title"],
        "price": deal_info["price"]["amount"],
        "regular_price": deal_info["regular"]["amount"],
        "discount": deal_info["cut"]
    }

    previous_state = history.get(deal_id)

    if previous_state == current_state:
        continue

    new_deals.append({
        "deal": deal,
        "state": current_state
    })


print(f"New or changed deals: {len(new_deals)}")


# -------------------------
# Create Discord embeds
# -------------------------

embeds = []

for item in new_deals:

    deal = item["deal"]
    deal_info = deal["deal"]

    title = deal["title"]
    price = deal_info["price"]["amount"]
    regular_price = deal_info["regular"]["amount"]
    discount = deal_info["cut"]
    currency = deal_info["price"]["currency"]
    url = deal_info["url"]

    assets = deal.get("assets", {})
    banner_url = assets.get("banner300")

    history_low = deal_info.get("historyLow", {})
    history_low_price = history_low.get("amount")

    expiry = deal_info.get("expiry")

    if expiry:
        expiry = expiry.replace("T", " ")[:16]

    description = (
        f"~~{regular_price:.2f} {currency}~~ → "
        f"**{price:.2f} {currency}**\n\n"
        f"📉 **History Low:** "
        f"{history_low_price:.2f} {currency}\n"
        f"⏰ **Sale Ends:** {expiry or 'Unknown'}"
    )

    embed = {
        "title": f"{discount}% OFF — {title}",
        "description": description,
        "url": url,
        "color": 5763719,
        "image": {
            "url": banner_url
        } if banner_url else None,
        "footer": {
            "text": "Steam deal • IsThereAnyDeal"
        }
    }

    embeds.append(embed)


# -------------------------
# Nothing new
# -------------------------

if not embeds:
    print("No new or changed deals.")
    print("Nothing to send.")
    raise SystemExit(0)


# -------------------------
# Send embeds in batches
# -------------------------

BATCH_SIZE = 10

total_batches = (
    len(embeds) + BATCH_SIZE - 1
) // BATCH_SIZE

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

    # --------------------------------
    # Save history ONLY after success
    # --------------------------------

    batch_start = start
    batch_end = start + len(batch)

    for item in new_deals[batch_start:batch_end]:

        deal = item["deal"]
        deal_id = str(deal["id"])

        history[deal_id] = item["state"]

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            history,
            file,
            indent=2,
            ensure_ascii=False
        )

    time.sleep(1)


print()
print("All new or changed deals sent successfully!")
