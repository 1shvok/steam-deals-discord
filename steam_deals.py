import json
from datetime import datetime, timezone, timedelta

from itad_api import get_deals
from deal_filters import get_game_deals, filter_new_deals
from discord_notifications import send_deal_notifications


def main():

    HISTORY_FILE = "sent_deals.json"
    HISTORY_RETENTION_DAYS = 14
    now = datetime.now(timezone.utc)

    # Здесь будет вся остальная логика программы


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
    # Send Discord notifications
    # -------------------------
    
    send_deal_notifications(
        new_deals,
        history,
        now,
        history_changed
    )

if __name__ == "__main__":
    main()
