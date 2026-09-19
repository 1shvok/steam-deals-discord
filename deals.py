import os
import requests

# =========================
# Settings
# =========================

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

API_URL = "https://www.cheapshark.com/api/1.0/deals"

MIN_DISCOUNT = 50
MAX_PAGES = 5
PAGE_SIZE = 60

headers = {
    "User-Agent": "SteamDealsDiscordBot/1.0"
}


# =========================
# Get Steam deals
# =========================

all_deals = []

for page in range(MAX_PAGES):

    params = {
        "storeID": "1",
        "onSale": "1",
        "pageNumber": page,
        "pageSize": PAGE_SIZE,
        "sortBy": "Savings",
        "desc": "1"
    }

    print(f"Checking CheapShark page {page + 1}...")

    response = requests.get(
        API_URL,
        params=params,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:
        print(f"CheapShark error: {response.status_code}")
        print(response.text)
        raise SystemExit(1)

    deals = response.json()

    if not deals:
        print("No more deals found.")
        break

    print(f"Received {len(deals)} deals.")

    all_deals.extend(deals)

    # If the API returned fewer than the maximum page size,
    # there are probably no more pages.
    if len(deals) < PAGE_SIZE:
        break


# =========================
# Filter deals
# =========================

qualified_deals = []

for deal in all_deals:

    try:
        savings = float(deal["savings"])
    except (KeyError, ValueError, TypeError):
        continue

    if savings >= MIN_DISCOUNT:
        qualified_deals.append(deal)


# Sort locally by discount
qualified_deals.sort(
    key=lambda deal: float(deal["savings"]),
    reverse=True
)


# =========================
# Debug information
# =========================

print(f"Total deals received: {len(all_deals)}")
print(f"Deals with {MIN_DISCOUNT}%+ discount: {len(qualified_deals)}")

# Show the highest discounts received
all_deals_sorted = sorted(
    all_deals,
    key=lambda deal: float(deal["savings"]),
    reverse=True
)

print("Highest discounts received:")

for deal in all_deals_sorted[:10]:
    print(
        f"- {deal['title']} | "
        f"{float(deal['savings']):.0f}% OFF | "
        f"${deal['salePrice']}"
    )

if qualified_deals:
    print("Qualifying deals:")

    for deal in qualified_deals[:10]:
        print(
            f"- {deal['title']} | "
            f"{float(deal['savings']):.0f}% OFF | "
            f"${deal['salePrice']}"
        )


# =========================
# No qualifying deals
# =========================

if not qualified_deals:
    print(
        f"No Steam deals with {MIN_DISCOUNT}%+ discount found."
    )
    raise SystemExit(0)


# =========================
# Select the best discount
# =========================

deal = qualified_deals[0]

title = deal["title"]
sale_price = deal["salePrice"]
normal_price = deal["normalPrice"]
savings = float(deal["savings"])
deal_id = deal["dealID"]
thumbnail = deal.get("thumb")


# =========================
# CheapShark deal link
# =========================

deal_url = (
    f"https://www.cheapshark.com/redirect"
    f"?dealID={deal_id}"
)


# =========================
# Discord Embed
# =========================

embed = {
    "title": f"🔥 {title}",
    "url": deal_url,

    "description": (
        f"**{savings:.0f}% OFF**\n\n"
        f"~~${normal_price}~~ → **${sale_price}**"
    ),

    "fields": [
        {
            "name": "Store",
            "value": "Steam",
            "inline": True
        },
        {
            "name": "Discount",
            "value": f"{savings:.0f}%",
            "inline": True
        }
    ],

    "footer": {
        "text": "Powered by CheapShark"
    }
}


# Add game image if available
if thumbnail:
    embed["thumbnail"] = {
        "url": thumbnail
    }


# =========================
# Send to Discord
# =========================

data = {
    "username": "Steam Deals",
    "embeds": [embed]
}


discord_response = requests.post(
    WEBHOOK_URL,
    json=data,
    timeout=30
)


# =========================
# Check Discord response
# =========================

if discord_response.status_code == 204:

    print(
        f"Deal sent successfully: "
        f"{title} | {savings:.0f}% OFF"
    )

else:

    print(
        f"Discord error: "
        f"{discord_response.status_code}"
    )

    print(discord_response.text)

    raise SystemExit(1)
