import os
import requests

API_KEY = os.environ["ITAD_API_KEY"]

URL = "https://api.isthereanydeal.com/deals/v2"

params = {
    "country": "PT",
    "shops": "61",
    "limit": 10,
    "sort": "-cut",
    "filter": '{"cut":{"min":50}}'
}

headers = {
    "ITAD-API-Key": API_KEY
}

response = requests.get(
    URL,
    params=params,
    headers=headers,
    timeout=30
)

print("Status:", response.status_code)

if response.status_code != 200:
    print(response.text)
    raise SystemExit(1)

data = response.json()

deals = data.get("list", [])

print(f"Deals received: {len(deals)}")
print()

for deal in deals:
    title = deal["title"]
    deal_info = deal["deal"]

    price = deal_info["price"]["amount"]
    regular_price = deal_info["regular"]["amount"]
    discount = deal_info["cut"]
    currency = deal_info["price"]["currency"]

    print(
        f"{title} | "
        f"{discount}% OFF | "
        f"{regular_price:.2f} {currency} -> {price:.2f} {currency}"
    )
