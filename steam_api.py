import json
import time
import re
import html
import requests
from bs4 import BeautifulSoup

# -------------------------
# Safe Steam reviews lookup
# -------------------------

STEAM_REVIEW_MIN_INTERVAL = 2.5
STEAM_REVIEW_MAX_ATTEMPTS = 3
STEAM_REVIEW_COOLDOWN_SECONDS = 300

_last_steam_review_request = 0.0
_steam_review_cooldown_until = 0.0

def get_steam_reviews(app_id):
    global _last_steam_review_request
    global _steam_review_cooldown_until

    # Stop sending requests if Steam has recently returned errors.
    if time.monotonic() < _steam_review_cooldown_until:
        return None

    url = (
        "https://api.steampowered.com/"
        "IUserReviewsService/GetAppReviews/v1/"
    )

    request_data = {
        "appid": int(app_id),
        "filter": 0,
        "languages": ["all"],
        "day_range": 0,
        "review_type": 0,
        "purchase_type": 1,
        "num_per_page": 1
    }

    params = {
        "input_json": json.dumps(request_data)
    }

    headers = {
        "Accept": "application/json"
    }

    for attempt in range(1, STEAM_REVIEW_MAX_ATTEMPTS + 1):

        wait_time = (
            STEAM_REVIEW_MIN_INTERVAL
            - (time.monotonic() - _last_steam_review_request)
        )

        if wait_time > 0:
            time.sleep(wait_time)

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=20
            )

            _last_steam_review_request = time.monotonic()

        except requests.RequestException as error:

            if attempt == STEAM_REVIEW_MAX_ATTEMPTS:
                _steam_review_cooldown_until = (
                    time.monotonic() + STEAM_REVIEW_COOLDOWN_SECONDS
                )

                print(
                    f"Steam reviews request failed for {app_id}: {error}"
                )
                return None

            delay = min(20, 3 * (2 ** (attempt - 1)))

            print(
                f"Steam reviews network error for {app_id}; "
                f"retrying in {delay}s."
            )

            time.sleep(delay)
            continue

        # Retry rate limits and temporary server errors.
        if (
            response.status_code in (403, 429)
            or 500 <= response.status_code < 600
        ):

            if attempt == STEAM_REVIEW_MAX_ATTEMPTS:
                _steam_review_cooldown_until = (
                    time.monotonic() + STEAM_REVIEW_COOLDOWN_SECONDS
                )

                print(
                    f"Steam reviews unavailable for {app_id}: "
                    f"HTTP {response.status_code}."
                )
                return None

            retry_after = response.headers.get("Retry-After")

            try:
                delay = min(60.0, max(2.0, float(retry_after)))
            except (TypeError, ValueError):
                delay = min(30, 3 * (2 ** (attempt - 1)))

            print(
                f"Steam reviews HTTP {response.status_code}; "
                f"retrying in {delay:g}s."
            )

            time.sleep(delay)
            continue

        if response.status_code != 200:
            print(
                f"Steam reviews request failed for {app_id}: "
                f"HTTP {response.status_code}."
            )
            return None

        try:
            api_data = response.json()

        except ValueError:

            if attempt == STEAM_REVIEW_MAX_ATTEMPTS:
                _steam_review_cooldown_until = (
                    time.monotonic() + STEAM_REVIEW_COOLDOWN_SECONDS
                )

                print(
                    f"Steam reviews returned invalid JSON for {app_id}."
                )
                return None

            delay = min(15, 3 * attempt)

            print(
                f"Steam reviews returned invalid JSON; "
                f"retrying in {delay}s."
            )

            time.sleep(delay)
            continue

        reviews_data = (
            api_data.get("response")
            if isinstance(api_data, dict)
            else None
        )

        query_summary = (
            reviews_data.get("query_summary")
            if isinstance(reviews_data, dict)
            else None
        )

        if not isinstance(query_summary, dict):

            if attempt == STEAM_REVIEW_MAX_ATTEMPTS:
                _steam_review_cooldown_until = (
                    time.monotonic() + STEAM_REVIEW_COOLDOWN_SECONDS
                )

                print(
                    f"Steam reviews response for {app_id} "
                    "does not contain query_summary."
                )
                return None

            delay = min(15, 3 * attempt)
            time.sleep(delay)
            continue

        try:
            total_reviews = int(
                query_summary.get("total_reviews", 0) or 0
            )
            total_positive = int(
                query_summary.get("total_positive", 0) or 0
            )
            total_negative = int(
                query_summary.get("total_negative", 0) or 0
            )

        except (TypeError, ValueError):
            print(
                f"Steam reviews returned invalid counts for {app_id}."
            )
            return None

        if (
            total_reviews <= 0
            or total_positive < 0
            or total_negative < 0
            or total_positive > total_reviews
            or total_negative > total_reviews
            or total_positive + total_negative > total_reviews
        ):
            print(
                f"Steam reviews returned inconsistent counts for {app_id}."
            )
            return None

        positive_percentage = (
            total_positive / total_reviews
        ) * 100

        return {
            "review_score_desc": query_summary.get("review_score_desc"),
            "total_reviews": total_reviews,
            "total_positive": total_positive,
            "total_negative": total_negative,
            "positive_percentage": positive_percentage
        }

    return None


# -------------------------
# Get Steam game metadata
# -------------------------

def get_steam_metadata(itad_url):

    try:
        steam_page = requests.get(
            itad_url,
            timeout=15,
            allow_redirects=True
        )

        match = re.search(
            r"store\.steampowered\.com/app/(\d+)",
            steam_page.url
        )

        if not match:
            return None

        app_id = match.group(1)

        # Get app details from Steam
        steam_response = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={
                "appids": app_id,
                "l": "english",
                "cc": "pt"
            },
            timeout=15
        )

        if steam_response.status_code != 200:
            return None

        steam_data = steam_response.json()
        app_data = steam_data.get(app_id, {})

        if not app_data.get("success"):
            return None

        game_data = app_data.get("data", {})

        app_type = game_data.get("type", "")

        description = game_data.get("short_description", "")
        # Steam header image, used if ITAD has no banner
        steam_header_image = game_data.get("header_image")
        description = re.sub(r"<[^>]+>", "", description)
        description = html.unescape(description)

        genres = [
            genre["description"]
            for genre in game_data.get("genres", [])
            if "description" in genre
        ]

        # Detect Steam Early Access games
        steam_categories = [
            category.get("description", "")
            for category in game_data.get("categories", [])
        ]

        early_access = any(
            "early access" in category.casefold()
            for category in steam_categories
        )

        # -------------------------
        # Check English language support
        # -------------------------

        supported_languages = game_data.get(
            "supported_languages",
            ""
        )

        language_text = BeautifulSoup(
            supported_languages,
            "html.parser"
        ).get_text(" ", strip=True)

        # Steam lists a language when the game supports it in some form.
        # The API text does not reliably separate interface/subtitles/audio.
        english_supported = bool(
            re.search(r"\bEnglish\b", language_text, re.IGNORECASE)
        )

        return {
            "type": app_type,
            "early_access": early_access,
            "description": description,
            "genres": genres,
            "english_supported": english_supported,
            "header_image": steam_header_image,
            "app_id": app_id
        }

    except Exception as error:

        print(f"Steam metadata error: {error}")

        return None
