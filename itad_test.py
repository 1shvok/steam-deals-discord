import json
import os
import time
import requests
import re
import html

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

        # Get app details from Steam
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

        app_type = game_data.get("type", "")

        description = game_data.get("short_description", "")
        description = re.sub(r"<[^>]+>", "", description)
        description = html.unescape(description)

        genres = [
            genre["description"]
            for genre in game_data.get("genres", [])
            if "description" in genre
        ]

        # Check English subtitles on the Steam store page
        from bs4 import BeautifulSoup

        store_response = requests.get(
            f"https://store.steampowered.com/app/{app_id}/",
            params={
                "l": "english",
                "cc": "pt"
            },
            timeout=15
        )

        english_subtitles = False

        if store_response.status_code == 200:

            soup = BeautifulSoup(
                store_response.text,
                "html.parser"
            )

            language_table = soup.select_one(
                "table.game_language_options"
            )

            if language_table:

                for row in language_table.select("tr"):

                    cells = row.find_all("td")

                    if len(cells) < 4:
                        continue

                    language = cells[0].get_text(
                        " ",
                        strip=True
                    )

                    subtitles_cell = cells[3]

                    subtitles_text = subtitles_cell.get_text(
                        " ",
                        strip=True
                    )

                    if (
                        language.lower().startswith("english")
                        and subtitles_text
                    ):
                        english_subtitles = True
                        break

        return {
            "type": app_type,
            "description": description,
            "genres": genres,
            "rating": None,
            "english_subtitles": english_subtitles
        }

    except Exception as error:

        print(f"Steam metadata error: {error}")

        return None

# -------------------------
# Filter using Steam metadata
# -------------------------

eligible_deals = []

for item in new_deals:

    deal = item["deal"]
    url = deal["deal"]["url"]

    metadata = get_steam_metadata(url)

    if not metadata:
        print(f"SKIPPED: Could not get Steam data: {deal['title']}")
        continue

    if metadata.get("type") != "game":
        print(
            f"SKIPPED: Not a full game: "
            f"{deal['title']} ({metadata.get('type')})"
        )
        continue

    if not metadata.get("english_subtitles"):
        print(
            f"SKIPPED: No confirmed English subtitles: "
            f"{deal['title']}"
        )
        continue

    item["steam_metadata"] = metadata
    eligible_deals.append(item)

print(
    f"Eligible games with English subtitles: "
    f"{len(eligible_deals)}"
)

new_deals = eligible_deals

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

    # Large banner at the bottom of the embed
    banner_url = assets.get("banner600")

    history_low = deal_info.get("historyLow", {})
    history_low_price = history_low.get("amount")

    expiry = deal_info.get("expiry")

    if expiry:
        expiry = expiry.replace("T", " ")[:16]

    # -------------------------
    # Get Steam metadata
    # -------------------------

    steam_metadata = item["steam_metadata"]

    game_description = ""
    genres = []
    rating = None

    if steam_metadata:

        game_description = (
            steam_metadata.get("description") or ""
        )

        genres = steam_metadata.get("genres", [])
        rating = steam_metadata.get("rating")

    # -------------------------
    # Genres as compact tags
    # -------------------------

    genre_text = "  ".join(
        f"`{genre}`"
        for genre in genres
    )

    # -------------------------
    # Main description
    # -------------------------

    description_parts = []

    # Game description immediately below the title
    if game_description:
        description_parts.append(
            f"*{game_description[:700]}*"
        )

    description_parts.append(
        f"**{discount}% OFF**"
    )

    description_parts.append(
        f"~~{regular_price:.2f} {currency}~~  →  **{price:.2f} {currency}**"
    )

    if genre_text:
        description_parts.append(genre_text)

    description_parts.append(
        f"[**View on Steam →**]({url})"
    )

    description = "\n\n".join(description_parts)

    # -------------------------
    # Embed fields
    # -------------------------

    fields = []

    if history_low_price is not None:

        fields.append({
            "name": "History Low",
            "value": f"{history_low_price:.2f} {currency}",
            "inline": True
        })

    fields.append({
        "name": "Sale Ends",
        "value": f"**{expiry or 'Unknown'}**",
        "inline": True
    })

    if rating is not None:

        fields.append({
            "name": "Metacritic",
            "value": f"**{rating}/100**",
            "inline": True
        })

    # -------------------------
    # Create embed
    # -------------------------

    embed = {
        "title": title,
        "description": description,
        "url": url,
        "color": 5763719,
        "fields": fields,
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
