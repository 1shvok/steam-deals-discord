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

print("Response type:", type(data).__name__)
print("Deals received:", len(data))

for i, deal in enumerate(data, 1):
    print(f"\n--- Deal {i} ---")
    print("ID:", deal.get("id"))

    if "title" in deal:
        print("Title:", deal["title"])

    if "current" in deal:
        current = deal["current"]

        print("Shop:", current["shop"]["name"])
        print("Discount:", current["cut"], "%")
        print(
            "Price:",
            current["price"]["amount"],
            current["price"]["currency"]
        )

    if "deals" in deal:
        for store_deal in deal["deals"]:
            print("Shop:", store_deal["shop"]["name"])
            print("Discount:", store_deal["cut"], "%")
            print(
                "Price:",
                store_deal["price"]["amount"],
                store_deal["price"]["currency"]
            )
