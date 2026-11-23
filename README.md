# Steam Deals Discord Bot

An automated Discord bot that tracks Steam game discounts and giveaways using the IsThereAnyDeal API.

The bot runs through GitHub Actions and sends notifications to Discord using a webhook.

## Features

### Steam Deals
- Tracks discounts on Steam games.
- Filters deals by minimum discount, review count and positive rating.
- Uses additional filters to identify potentially suspicious deals.
- Sends notifications for new or changed deals.
- Stores notification history to prevent duplicate messages.

### Steam Giveaways
- Tracks active giveaways.
- Filters giveaways to include Steam games.
- Sends notifications for new or changed giveaways.
- Stores giveaway history to prevent duplicate messages.

## Project Structure

- `steam_deals.py` — Main Steam deals tracker.
- `giveaways.py` — Steam giveaways tracker.
- `settings.py` — Bot configuration and filters.
- `history_store.py` — Safe JSON history storage.
- `steam_api.py` — Steam API requests, game metadata and reviews.
- `sent_deals.json` — Steam deals notification history.
- `sent_giveaways.json` — Giveaway notification history.
- `.github/workflows/steam_notifications.yml` — GitHub Actions workflow.
- `README.md` — Project documentation.

## Configuration

The bot settings are stored in `settings.py`.

Current deal filters:

- Minimum discount: 60%.
- Minimum Steam reviews: 700.
- Minimum positive rating: 70%.
- Indie filter mode: balanced.

Additional suspicious-game filters and ITAD pagination limits can also be configured in this file.

## Requirements

- Python 3.12.
- `requests`.
- `beautifulsoup4`.
- IsThereAnyDeal API key.
- Discord webhook URL.

## GitHub Secrets

The following repository secrets must be configured:

- `ITAD_API_KEY` — IsThereAnyDeal API key.
- `DISCORD_WEBHOOK_URL` — Discord channel webhook URL.

Never store API keys or webhook URLs directly in source code.

## Automation

The project uses GitHub Actions to:

1. Check out the repository.
2. Set up Python.
3. Install dependencies.
4. Run the Steam deals tracker.
5. Run the Steam giveaways tracker.
6. Save and commit updated notification history.

The workflow can also be started manually through GitHub Actions.

## Notification History

The JSON history files are essential for preventing duplicate notifications.

- `sent_deals.json`.
- `sent_giveaways.json`.

Both files must remain in the repository. The bot maintains their contents automatically.

---

**Powered by IsThereAnyDeal API.**
