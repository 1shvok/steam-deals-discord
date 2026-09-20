import os
import requests

API_KEY = os.environ["ITAD_API_KEY"]

URL = "https://api.isthereanydeal.com/deals/v2"

params = {
    "country": "PT",
    "shops": "61",
    "limit": 10,
    "sort": "-cut",
    "filter": '{"cut":{"min":50,"max":null}}'
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

print("Deals received:", len(data))

for deal in data:
    print(
        f"{deal['title']} | "
        f"{deal['deal']['cut']}% OFF | "
        f"{deal['deal']['price']['amount']} "
        f"{deal['deal']['price']['currency']}"
    )
