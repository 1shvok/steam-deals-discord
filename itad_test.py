import json
import os
import time
import requests
import re
import html
from bs4 import BeautifulSoup

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
        # Steam header image, used if ITAD has no banner
        steam_header_image = game_data.get("header_image")
        description = re.sub(r"<[^>]+>", "", description)
        description = html.unescape(description)

        genres = [
            genre["description"]
            for genre in game_data.get("genres", [])
            if "description" in genre
        ]

        # Detect Steam Early Access games
        steam_categories = [
            category.get("description", "")
            for category in game_data.get("categories", [])
        ]

        early_access = any(
            "early access" in category.casefold()
            for category in steam_categories
        )

        # -------------------------
        # Check English language support
        # -------------------------

        supported_languages = game_data.get(
            "supported_languages",
            ""
        )

        language_text = BeautifulSoup(
            supported_languages,
            "html.parser"
        ).get_text(" ", strip=True)

        # Steam lists a language when the game supports it in some form.
        # The API text does not reliably separate interface/subtitles/audio.
        english_supported = bool(
            re.search(r"\bEnglish\b", language_text, re.IGNORECASE)
        )

        # Get Steam's aggregate user review score and review count.
        # Reviews are optional: a failure here must not block the deal.
        review_score_desc = None
        total_reviews = 0

        try:
            reviews_response = requests.get(
                f"https://store.steampowered.com/appreviews/{app_id}",
                params={
                    "json": 1,
                    "language": "all",
                    "filter": "all",
                    "review_type": "all",
                    "num_per_page": 1
                },
                timeout=15
            )

            if reviews_response.status_code == 200:
                try:
                    reviews_data = reviews_response.json()
                except ValueError:
                    print(
                        f"Steam reviews error for {app_id}: "
                        "Invalid JSON response"
                    )
                else:
                    query_summary = reviews_data.get("query_summary")

                    if query_summary:
                        review_score_desc = query_summary.get(
                            "review_score_desc"
                        )
                        total_reviews = query_summary.get(
                            "total_reviews", 0
                        )

                        if not review_score_desc or not total_reviews:
                            print(
                                f"Steam reviews: no aggregate rating "
                                f"for app {app_id}"
                            )
                    else:
                        print(
                            f"Steam reviews error for {app_id}: "
                            "query_summary missing"
                        )

            else:
                print(
                    f"Steam reviews error for {app_id}: "
                    f"HTTP {reviews_response.status_code} — "
                    f"{reviews_response.text[:300]}"
                )

        except requests.RequestException as error:
            print(
                f"Steam reviews request failed for {app_id}: {error}"
            )

        return {
            "type": app_type,
            "early_access": early_access,
            "description": description,
            "genres": genres,
            "review_score_desc": review_score_desc,
            "total_reviews": total_reviews,
            "english_supported": english_supported,
            "header_image": steam_header_image,
            "app_id": app_id
        }

    except Exception as error:

        print(f"Steam metadata error: {error}")

        return None

# -------------------------
# Filter special editions
# -------------------------

import re

EDITION_PATTERN = re.compile(
    r"\b("
    r"gold|premium|deluxe|ultimate|"
    r"complete|collector'?s|definitive|"
    r"anniversary|special|limited|"
    r"game of the year|goty"
    r")\s+edition\b",
    re.IGNORECASE
)

def is_special_edition(title):
    return bool(EDITION_PATTERN.search(title))

# -------------------------
# Filter using Steam metadata
# -------------------------

eligible_deals = []

for item in new_deals:

    deal = item["deal"]
    url = deal["deal"]["url"]

    if is_special_edition(deal["title"]):
        print(f"SKIPPED: Special edition: {deal['title']}")
        continue

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

    if metadata.get("early_access"):
        print(
            f"SKIPPED: Early Access game: {deal['title']}"
        )
        continue

    review_score_desc = metadata.get("review_score_desc")
    total_reviews = metadata.get("total_reviews") or 0

    if not review_score_desc or total_reviews <= 0:
        print(
            f"SKIPPED: No Steam reviews: {deal['title']}"
        )
        continue

    if "negative" in review_score_desc.casefold():
        print(
            f"SKIPPED: Negative Steam reviews "
            f"({review_score_desc}): {deal['title']}"
        )
        continue

    if not metadata.get("english_supported"):
        print(
            f"SKIPPED: No English language support listed: "
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
    # Use Steam header image if ITAD has no banner
    if not banner_url and steam_metadata:
        banner_url = steam_metadata.get("header_image")

    game_description = ""
    genres = []
    review_score_desc = None
    total_reviews = 0

    if steam_metadata:

        game_description = (
            steam_metadata.get("description") or ""
        )

        genres = steam_metadata.get("genres", [])
        review_score_desc = steam_metadata.get("review_score_desc")
        total_reviews = steam_metadata.get("total_reviews", 0)

    # -------------------------
    # Genres as compact tags
    # -------------------------

    # Colored markers for game genres
    genre_colors = {
        "action": "🔴",
        "adventure": "🟠",
        "indie": "🟣",
        "casual": "🟢",
        "rpg": "🔵",
        "strategy": "🟡",
        "simulation": "🟤",
        "sports": "⚽",
        "racing": "🟠",
        "massively multiplayer": "🔵",
        "free to play": "🟢",
        "early access": "🟡",
        "horror": "🟣",
        "platformer": "🟠",
    }

    genre_text = "  ".join(
        f"{genre_colors.get(genre.casefold(), '⚪')} `{genre}`"
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

    # Discount and Steam reviews on the same line
    discount_line = f"**{discount}% OFF**"

    if review_score_desc and total_reviews:
        discount_line += (
            f"　　　　　`{review_score_desc}` · {total_reviews:,} reviews"
        )

    description_parts.append(discount_line)

    # Price on its own line
    price_line = (
        f"~~{regular_price:.2f} {currency}~~ → **{price:.2f} {currency}**"
    )

    description_parts.append(price_line)

    # Genres as compact tags
    if genre_text:
        description_parts.append(genre_text)

    # Use a normal HTTPS Steam link
    app_id = steam_metadata.get("app_id") if steam_metadata else None

    if app_id:
        steam_url = f"https://store.steampowered.com/app/{app_id}"
    else:
        steam_url = url

    description_parts.append(
        f"[**View on Steam →**]({steam_url})"
    )

    description = "\n\n".join(description_parts)

    # -------------------------
    # Embed fields
    # -------------------------

    # Keep discount and price as separate fields; place reviews immediately after them.
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
# Send embeds in safe batches
# -------------------------

MAX_EMBEDS_PER_MESSAGE = 10
MAX_MESSAGE_CHARS = 5500  # запас до лимита Discord в 6000 символов


def get_embed_text_length(embed):
    """Count text characters that contribute to Discord's embed limit."""
    total = len(embed.get("title") or "")
    total += len(embed.get("description") or "")

    for field in embed.get("fields", []):
        total += len(field.get("name") or "")
        total += len(field.get("value") or "")

    footer = embed.get("footer") or {}
    total += len(footer.get("text") or "")

    author = embed.get("author") or {}
    total += len(author.get("name") or "")

    return total


# Each entry keeps the embed together with its corresponding deal.
batches = []
current_batch = []
current_chars = 0

for item, embed in zip(new_deals, embeds):
    embed_chars = get_embed_text_length(embed)

    # A single embed must fit by itself.
    if embed_chars > MAX_MESSAGE_CHARS:
        print(
            f"SKIPPED: Embed is too large ({embed_chars} characters): "
            f"{item['deal']['title']}"
        )
        continue

    would_exceed_limit = (
        current_chars + embed_chars > MAX_MESSAGE_CHARS
        or len(current_batch) >= MAX_EMBEDS_PER_MESSAGE
    )

    if current_batch and would_exceed_limit:
        batches.append(current_batch)
        current_batch = []
        current_chars = 0

    current_batch.append((item, embed))
    current_chars += embed_chars

if current_batch:
    batches.append(current_batch)

print(f"Discord batches: {len(batches)}")


for batch_number, batch_items in enumerate(batches, start=1):

    batch_embeds = [embed for item, embed in batch_items]

    payload = {
        "embeds": batch_embeds
    }

    while True:

        discord_response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=30
        )

        if discord_response.status_code in (200, 204):

            print(
                f"Batch {batch_number}/{len(batches)} "
                f"sent successfully ({len(batch_embeds)} deals)."
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

    # Save only deals from this successfully sent batch.
    for item, embed in batch_items:
        deal_id = str(item["deal"]["id"])
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
