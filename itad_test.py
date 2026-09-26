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
# Get Steam game metadata
# -------------------------

import re


def get_steam_metadata(itad_url):

    try:
        steam_page = requests.get(
            itad_url,
            timeout=15,
            allow_redirects=True
        )

        match = re.search(
            r"store\.steampowered\.com/app/(\d+)",
            steam_page.url
        )

        if not match:
            return None

        app_id = match.group(1)

        steam_response = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={
                "appids": app_id,
                "l": "english",
                "cc": "pt"
            },
            timeout=15
        )

        if steam_response.status_code != 200:
            return None

        steam_data = steam_response.json()
        app_data = steam_data.get(app_id, {})

        if not app_data.get("success"):
            return None

        game_data = app_data.get("data", {})

        description = game_data.get("short_description", "")

        genres = [
            genre["description"]
            for genre in game_data.get("genres", [])
            if "description" in genre
        ]

        return {
            "description": description,
            "genres": genres
        }

    except Exception as error:

        print(
            f"Steam metadata error: {error}"
        )

        return None

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
    banner_url = assets.get("banner600")

    history_low = deal_info.get("historyLow", {})
    history_low_price = history_low.get("amount")

    expiry = deal_info.get("expiry")

    if expiry:
        expiry = expiry.replace("T", " ")[:16]

    # -------------------------
    # Get Steam metadata
    # -------------------------

    steam_metadata = get_steam_metadata(url)

    game_description = ""
    genres = []

    if steam_metadata:

        game_description = (
            steam_metadata.get("description") or ""
        )

        genres = steam_metadata.get(
            "genres",
            []
        )

    # -------------------------
    # Build description
    # -------------------------

    description_parts = []

    description_parts.append(
        f"**🔥 {discount}% OFF**"
    )

    description_parts.append(
        f"**~~{regular_price:.2f} {currency}~~ "
        f"→ {price:.2f} {currency}**"
    )

    description_parts.append(
        f"📉 **History Low:** "
        f"{history_low_price:.2f} {currency}"
        if history_low_price is not None
        else
        "📉 **History Low:** Unknown"
    )

    description_parts.append(
        f"⏰ **Sale Ends:** "
        f"{expiry or 'Unknown'}"
    )

    if genres:

        genre_text = " • ".join(genres)

        description_parts.append(
            f"🎮 **Genres:** {genre_text}"
        )

    if game_description:

        description_parts.append(
            f"*{game_description}*"
        )

    description_parts.append(
        f"[**🔗 View on Steam →**]({url})"
    )

    description = "\n\n".join(
        description_parts
    )

    # -------------------------
    # Create embed
    # -------------------------

    embed = {
        "title": title,
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
