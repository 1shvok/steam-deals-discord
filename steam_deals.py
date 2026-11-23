import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from itad_api import get_deals
from deal_filters import get_game_deals, filter_new_deals
from history_store import save_json_atomic

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

HISTORY_FILE = "sent_deals.json"


# -------------------------
# Load sent deals history
# -------------------------

HISTORY_RETENTION_DAYS = 14
now = datetime.now(timezone.utc)

try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        history = json.load(file)

    if not isinstance(history, dict):
        print("ERROR: History file is not a dictionary. Aborting run.")
        raise SystemExit(1)

except FileNotFoundError:
    # A missing history file is allowed on the first run.
    history = {}

except json.JSONDecodeError as error:
    print(f"ERROR: History file is corrupted: {error}")
    print("Aborting to prevent duplicate deal notifications.")
    raise SystemExit(1)

except OSError as error:
    print(f"ERROR: Could not read history file: {error}")
    raise SystemExit(1)


# Migrate old history format to the new format.
for deal_id, entry in list(history.items()):

    if not isinstance(entry, dict):
        del history[deal_id]
        continue

    if "state" in entry:
        continue

    # Old format: the entry itself was the deal state.
    history[deal_id] = {
        "state": entry,
        "last_seen": now.isoformat(),
        "last_sent": now.isoformat()
    }


print(f"Previously sent deals: {len(history)}")

# -------------------------
# Get deals from ITAD
# -------------------------

deals = get_deals()

# -------------------------
# Filter games only
# -------------------------

games = get_game_deals(deals)


# -------------------------
# Update history visibility
# -------------------------

current_game_ids = {
    str(deal.get("id"))
    for deal in games
    if deal.get("id") is not None
}

history_changed = False

for deal_id in current_game_ids:

    entry = history.get(deal_id)

    if isinstance(entry, dict):
        entry["last_seen"] = now.isoformat()
        history_changed = True

# Remove deals that have not appeared in ITAD for 14 days.
cutoff = now - timedelta(days=HISTORY_RETENTION_DAYS)

for deal_id, entry in list(history.items()):

    if not isinstance(entry, dict):
        del history[deal_id]
        continue

    if deal_id in current_game_ids:
        continue

    last_seen_text = entry.get("last_seen")

    if not last_seen_text:
        # Old/corrupted entry without a timestamp.
        # Keep it for now instead of accidentally deleting it.
        continue

    try:
        last_seen = datetime.fromisoformat(last_seen_text)

        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        if last_seen < cutoff:
            print(
                f"REMOVED FROM HISTORY: "
                f"{deal_id} (not seen for {HISTORY_RETENTION_DAYS} days)"
            )
            del history[deal_id]
            history_changed = True

    except (ValueError, TypeError):
        print(
            f"WARNING: Invalid last_seen timestamp for {deal_id}. "
            "Keeping entry."
        )

print(f"History after cleanup: {len(history)}")


# -------------------------
# Find new or changed deals
# -------------------------

new_deals = []

for deal in games:

    deal_id = str(deal["id"])
    deal_info = deal["deal"]

    expiry = deal_info.get("expiry")

    current_state = {
        "title": deal["title"],
        "price": deal_info["price"]["amount"],
        "regular_price": deal_info["regular"]["amount"],
        "discount": deal_info["cut"],
        "expiry": expiry
    }

    previous_entry = history.get(deal_id)
    previous_state = (
        previous_entry.get("state")
        if isinstance(previous_entry, dict)
        else None
    )

    if previous_state == current_state:
        continue

    new_deals.append({
        "deal": deal,
        "state": current_state
    })


print(f"New or changed deals: {len(new_deals)}")

# -------------------------
# Filter new deals
# -------------------------

new_deals = filter_new_deals(new_deals)


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
        try:
            expiry_datetime = datetime.fromisoformat(
                expiry.replace("Z", "+00:00")
            )
            expiry = expiry_datetime.strftime("%d.%m.%Y     %H:%M")
        except ValueError:
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

    genre_text = "  ".join(
        f"`{genre.upper()}`"
        for genre in genres
    )

    # -------------------------
    # Main description
    # -------------------------

    description_parts = []

    # Game description with Discord's quote styling
    if game_description:
        quoted_description = "\n".join(
            f"> *{line}*"
            for line in game_description[:700].strip().splitlines()
        )

        description_parts.append(quoted_description)

    # Discount and Steam reviews on the same line
    discount_line = f"**{discount}% OFF**"

    if review_score_desc and total_reviews:
        discount_line += (
            f"　　        　　　`{review_score_desc}` · {total_reviews:,} reviews"
        )

    description_parts.append(discount_line)
    currency_display = "€" if currency == "EUR" else currency

    # Price on its own line
    price_line = (
        f"~~{regular_price:.2f} {currency_display}~~ → "
        f"**{price:.2f} {currency_display}**"
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
            "name": "**History Low**",
            "value": f"{history_low_price:.2f} {currency_display}",
            "inline": True
        })

    fields.append({
        "name": "**Sale Ends**",
        "value": f"{expiry or 'Unknown'}",
        "inline": True
    })

    # -------------------------
    # Create embed
    # -------------------------

    embed = {
        "title": title,
        "description": description,
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

    if history_changed:
        save_json_atomic(HISTORY_FILE, history)
        print("History changes saved.")

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

        history[deal_id] = {
            "state": item["state"],
            "last_seen": now.isoformat(),
            "last_sent": now.isoformat()
        }

    save_json_atomic(HISTORY_FILE, history)

    time.sleep(1)


print()
print("All new or changed deals sent successfully!")
