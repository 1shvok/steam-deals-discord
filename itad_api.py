import json
import os
import requests

from settings import (
    ITAD_COUNTRY,
    STEAM_SHOP_ID,
    MIN_DISCOUNT_PERCENT,
    ITAD_PAGE_LIMIT,
    ITAD_MAX_PAGES
)


ITAD_URL = "https://api.isthereanydeal.com/deals/v2"


def get_deals():

    api_key = os.environ["ITAD_API_KEY"]

    params = {
        "country": ITAD_COUNTRY,
        "shops": str(STEAM_SHOP_ID),
        "limit": ITAD_PAGE_LIMIT,
        "sort": "-cut",
        "filter": json.dumps({
            "cut": {
                "min": MIN_DISCOUNT_PERCENT
            }
        })
    }

    headers = {
        "ITAD-API-Key": api_key
    }

    deals = []
    seen_deal_ids = set()
    offset = 0

    for page_number in range(1, ITAD_MAX_PAGES + 1):

        page_params = params.copy()
        page_params["offset"] = offset

        response = requests.get(
            ITAD_URL,
            params=page_params,
            headers=headers,
            timeout=30
        )

        print(
            f"ITAD page {page_number} status:",
            response.status_code
        )

        if response.status_code != 200:
            print(response.text)
            raise SystemExit(1)

        try:
            data = response.json()
        except ValueError:
            print("ERROR: ITAD returned invalid JSON. Aborting run.")
            raise SystemExit(1)

        if not isinstance(data, dict):
            print("ERROR: ITAD returned an unexpected response format.")
            raise SystemExit(1)

        page_deals = data.get("list")

        if not isinstance(page_deals, list):
            print("ERROR: ITAD response does not contain a valid deals list.")
            raise SystemExit(1)

        has_more = data.get("hasMore")

        if not isinstance(has_more, bool):
            print("ERROR: ITAD pagination field 'hasMore' is invalid.")
            raise SystemExit(1)

        if not page_deals:
            if page_number == 1:
                print("ERROR: ITAD returned an empty deals list.")
                raise SystemExit(1)

            if has_more:
                print("ERROR: ITAD reports more pages but returned an empty page.")
                raise SystemExit(1)

            break

        for deal in page_deals:

            if not isinstance(deal, dict):
                print("ERROR: ITAD returned an invalid deal entry.")
                raise SystemExit(1)

            deal_id = deal.get("id")

            if not isinstance(deal_id, str) or not deal_id:
                print("ERROR: ITAD returned a deal without a valid ID.")
                raise SystemExit(1)

            if deal_id in seen_deal_ids:
                continue

            seen_deal_ids.add(deal_id)
            deals.append(deal)

        print(
            f"Page {page_number}: received {len(page_deals)} deals, "
            f"unique total: {len(deals)}"
        )

        if not has_more:
            break

        next_offset = data.get("nextOffset")

        if (
            not isinstance(next_offset, int)
            or isinstance(next_offset, bool)
            or next_offset <= offset
        ):
            print("ERROR: ITAD returned an invalid nextOffset.")
            raise SystemExit(1)

        if page_number == ITAD_MAX_PAGES:
            print("Maximum ITAD page limit reached.")
            break

        offset = next_offset

    if not deals:
        print("ERROR: No deals collected. Aborting to protect history.")
        raise SystemExit(1)

    print(f"Total unique deals received: {len(deals)}")

    return deals
