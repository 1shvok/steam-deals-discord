import os
import time
import requests

from datetime import datetime
from history_store import save_json_atomic


HISTORY_FILE = "sent_deals.json"

MAX_EMBEDS_PER_MESSAGE = 10
MAX_MESSAGE_CHARS = 5500  # запас до лимита Discord в 6000 символов


# -------------------------
# Create Discord embeds
# -------------------------

def create_deal_embeds(new_deals):

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

    return embeds


# -------------------------
# Calculate embed text length
# -------------------------

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


# -------------------------
# Group embeds into safe batches
# -------------------------

def create_batches(new_deals, embeds):

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

    return batches


# -------------------------
# Send Discord notifications
# -------------------------

def send_deal_notifications(new_deals, history, now, history_changed):

    embeds = create_deal_embeds(new_deals)

    # Nothing new
    if not embeds:

        if history_changed:
            save_json_atomic(HISTORY_FILE, history)
            print("History changes saved.")

        print("No new or changed deals.")
        print("Nothing to send.")
        raise SystemExit(0)

    # Create safe batches
    batches = create_batches(new_deals, embeds)

    print(f"Discord batches: {len(batches)}")

    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

    for batch_number, batch_items in enumerate(batches, start=1):

        batch_embeds = [embed for item, embed in batch_items]

        payload = {
            "embeds": batch_embeds
        }

        while True:

            discord_response = requests.post(
                webhook_url,
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
