import json
import os
import time
import requests

from datetime import datetime, timezone, timedelta
from settings import STEAM_SHOP_ID


# -------------------------
# General settings
# -------------------------

API_URL = "https://api.isthereanydeal.com/giveaways/v1"
HISTORY_FILE = "sent_giveaways.json"

PAGE_LIMIT = 50
MAX_PAGES = 20
HISTORY_RETENTION_DAYS = 14

API_KEY = os.environ["ITAD_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

HEADERS = {
    "ITAD-API-Key": API_KEY
}

now = datetime.now(timezone.utc)


# -------------------------
# Load giveaway history
# -------------------------

try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        history = json.load(file)

    if not isinstance(history, dict):
        print("ERROR: Giveaway history is not a dictionary.")
        raise SystemExit(1)

except FileNotFoundError:
    history = {}

except json.JSONDecodeError as error:
    print(f"ERROR: Giveaway history is corrupted: {error}")
    raise SystemExit(1)

except OSError as error:
    print(f"ERROR: Could not read giveaway history: {error}")
    raise SystemExit(1)


def save_history():
    temporary_file = HISTORY_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            history,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(temporary_file, HISTORY_FILE)


# -------------------------
# Get active giveaways
# -------------------------

giveaways = []
seen_ids = set()

offset = 0

for page_number in range(1, MAX_PAGES + 1):

    params = {
        "offset": offset,
        "limit": PAGE_LIMIT,
        "mature": "false",
        "expired": "false",
        "sort": "-publish"
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            headers=HEADERS,
            timeout=30
        )

    except requests.RequestException as error:
        print(f"ERROR: ITAD giveaways request failed: {error}")
        raise SystemExit(1)

    print(
        f"Giveaways page {page_number} status:",
        response.status_code
    )

    if response.status_code != 200:
        print(response.text)
        raise SystemExit(1)

    try:
        page_data = response.json()

    except ValueError:
        print("ERROR: ITAD returned invalid JSON.")
        raise SystemExit(1)

    if not isinstance(page_data, list):
        print("ERROR: Unexpected giveaways response format.")
        raise SystemExit(1)

    if not page_data:
        break

    for giveaway in page_data:

        if not isinstance(giveaway, dict):
            print("ERROR: Invalid giveaway entry.")
            raise SystemExit(1)

        giveaway_id = giveaway.get("id")

        if (
            not isinstance(giveaway_id, int)
            or isinstance(giveaway_id, bool)
        ):
            print("ERROR: Giveaway has an invalid ID.")
            raise SystemExit(1)

        if giveaway_id in seen_ids:
            continue

        seen_ids.add(giveaway_id)
        giveaways.append(giveaway)

    print(
        f"Page {page_number}: received {len(page_data)} "
        f"giveaways, unique total: {len(giveaways)}"
    )

    if len(page_data) < PAGE_LIMIT:
        break

    offset += len(page_data)

else:
    print("WARNING: Maximum giveaway page limit reached.")

print(f"Total giveaways received: {len(giveaways)}")


# -------------------------
# Filter Steam giveaways
# -------------------------

steam_giveaways = []

for giveaway in giveaways:

    shop = giveaway.get("shop")

    if not isinstance(shop, dict):
        continue

    if shop.get("id") != STEAM_SHOP_ID:
        continue

    games = giveaway.get("games")

    if not isinstance(games, list):
        print(
            f"WARNING: Invalid games list in giveaway "
            f"{giveaway.get('id')}."
        )
        continue

    full_games = [
        game for game in games
        if (
            isinstance(game, dict)
            and game.get("type") == "game"
            and isinstance(game.get("title"), str)
        )
    ]

    if not full_games:
        continue

    steam_giveaways.append({
        "data": giveaway,
        "games": full_games
    })

print(f"Active Steam giveaways: {len(steam_giveaways)}")


# -------------------------
# Update history visibility
# -------------------------

current_ids = {
    str(item["data"]["id"])
    for item in steam_giveaways
}

history_changed = False


cutoff = now - timedelta(days=HISTORY_RETENTION_DAYS)

for giveaway_id, entry in list(history.items()):

    if not isinstance(entry, dict):
        print(
            f"ERROR: Invalid history entry for {giveaway_id}."
        )
        raise SystemExit(1)

    if giveaway_id in current_ids:
        continue

    last_seen_text = (
        entry.get("last_seen")
        or entry.get("last_sent")
    )

    if not last_seen_text:
        continue

    try:
        last_seen = datetime.fromisoformat(last_seen_text)

        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        if last_seen < cutoff:
            del history[giveaway_id]
            history_changed = True

    except (ValueError, TypeError):
        print(
            f"WARNING: Invalid timestamp for giveaway "
            f"{giveaway_id}. Keeping history entry."
        )


# -------------------------
# Find new giveaways
# -------------------------

new_giveaways = []

for item in steam_giveaways:

    giveaway = item["data"]
    games = item["games"]

    giveaway_id = str(giveaway["id"])

    game_titles = [
        game["title"]
        for game in games
    ]

    current_state = {
        "title": giveaway.get("title"),
        "games": game_titles,
        "expiry": giveaway.get("expiry"),
        "url": giveaway.get("url")
    }

    previous_entry = history.get(giveaway_id)

    previous_state = (
        previous_entry.get("state")
        if isinstance(previous_entry, dict)
        else None
    )

    if previous_state == current_state:
        continue

    new_giveaways.append({
        "id": giveaway_id,
        "data": giveaway,
        "games": games,
        "state": current_state
    })

print(f"New or changed Steam giveaways: {len(new_giveaways)}")


# -------------------------
# Create and send notifications
# -------------------------

for item in new_giveaways:

    giveaway = item["data"]
    games = item["games"]

    title = giveaway.get("title") or "Steam Giveaway"
    url = giveaway.get("url")
    details_url = giveaway.get("details")
    expiry = giveaway.get("expiry")

    if not isinstance(url, str) or not url.startswith("https://"):
        print(
            f"SKIPPED: Invalid giveaway URL: {title}"
        )
        continue

    game_titles = "\n".join(
        f"• {game['title']}"
        for game in games
    )

    if len(game_titles) > 3000:
        game_titles = game_titles[:2990] + "..."

    description_parts = [
        "**FREE ON STEAM**",
        game_titles,
        f"[Claim giveaway]({url})"
    ]

    if isinstance(details_url, str) and details_url.startswith("https://"):
        description_parts.append(
            f"[View on IsThereAnyDeal]({details_url})"
        )

    description = "\n\n".join(description_parts)

    fields = []

    if expiry:
        fields.append({
            "name": "Ends",
            "value": str(expiry),
            "inline": True
        })

    embed = {
        "title": title[:256],
        "description": description,
        "color": 5763719,
        "fields": fields,
        "footer": {
            "text": "Steam giveaway • IsThereAnyDeal"
        }
    }

    first_game_assets = games[0].get("assets", {})

    if isinstance(first_game_assets, dict):
        banner = first_game_assets.get("banner600")

        if isinstance(banner, str) and banner.startswith("https://"):
            embed["image"] = {
                "url": banner
            }

    payload = {
        "embeds": [embed]
    }

    # Send with Discord rate-limit handling.
    while True:

        try:
            discord_response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=30
            )

        except requests.RequestException as error:
            print(f"ERROR: Discord request failed: {error}")
            raise SystemExit(1)

        if discord_response.status_code in (200, 204):
            print(f"Giveaway sent: {title}")
            break

        if discord_response.status_code == 429:

            try:
                retry_data = discord_response.json()
                retry_after = float(
                    retry_data.get("retry_after", 1)
                )
            except (ValueError, TypeError):
                retry_after = 1

            print(
                f"Discord rate limit. Waiting "
                f"{retry_after} seconds..."
            )

            time.sleep(retry_after + 0.2)
            continue

        print("Discord error:")
        print(discord_response.text)
        raise SystemExit(1)

    # Save only after successful delivery.
    history[item["id"]] = {
        "state": item["state"],
        "last_seen": now.isoformat(),
        "last_sent": now.isoformat()
    }

    save_history()

    time.sleep(1)


# -------------------------
# Save history changes
# -------------------------

if not new_giveaways and history_changed:
    save_history()

print()
print("Steam giveaway check completed.")
