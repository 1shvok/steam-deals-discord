import re

from steam_api import get_steam_reviews, get_steam_metadata


# -------------------------
# Deal filter settings
# -------------------------

MIN_DISCOUNT_PERCENT = 60
MIN_STEAM_REVIEWS = 700
MIN_STEAM_POSITIVE_PERCENT = 70

INDIE_FILTER_MODE = "balanced"

# -------------------------
# Suspicious-game filter settings
# -------------------------

SUSPICIOUS_HIGH_PRICE = 100.0
SUSPICIOUS_EXTREME_DISCOUNT = 90
SUSPICIOUS_HISTORY_LOW_MULTIPLIER = 1.2
SUSPICIOUS_MANY_GENRES = 8
SUSPICIOUS_LOW_REVIEW_COUNT = 500
SUSPICIOUS_LOW_POSITIVE_PERCENT = 80
SUSPICIOUS_MIN_SIGNALS = 3


# -------------------------
# Filter game deals only
# -------------------------

def get_game_deals(deals):

    games = []

    for deal in deals:

        if deal.get("type") != "game":
            continue

        games.append(deal)

    print(f"Game deals: {len(games)}")

    return games


# -------------------------
# Filter special editions
# -------------------------

EDITION_PATTERN = re.compile(
    r"\b("
    r"gold|premium|deluxe|ultimate|"
    r"complete|collector'?s|definitive|"
    r"anniversary|special|limited|"
    r"game of the year|goty"
    r")\s+edition\b",
    re.IGNORECASE
)


def is_special_edition(title):
    return bool(EDITION_PATTERN.search(title))


# -------------------------
# Detect suspicious games
# -------------------------

def is_suspicious_game(deal, metadata, reviews):

    deal_info = deal.get("deal", {})

    price_data = deal_info.get("price", {})
    regular_data = deal_info.get("regular", {})
    history_low_data = deal_info.get("historyLow", {})

    try:
        current_price = float(price_data.get("amount"))
        regular_price = float(regular_data.get("amount"))
        discount = float(deal_info.get("cut"))

    except (TypeError, ValueError):
        print(
            f"WARNING: Invalid pricing data for {deal.get('title')}."
        )
        return False

    signals = []

    # Signal 1: High regular price combined with an extreme discount.
    if (
        regular_price >= SUSPICIOUS_HIGH_PRICE
        and discount >= SUSPICIOUS_EXTREME_DISCOUNT
    ):
        signals.append("high regular price + extreme discount")

    # Signal 2: Current price is significantly above the historical low.
    try:
        history_low = float(history_low_data.get("amount"))
    except (TypeError, ValueError, AttributeError):
        history_low = None

    if (
        history_low is not None
        and history_low > 0
        and current_price > (
            history_low * SUSPICIOUS_HISTORY_LOW_MULTIPLIER
        )
    ):
        signals.append("price above historical low")

    # Signal 3: An unusually large number of genres.
    genres = metadata.get("genres", [])

    if (
        isinstance(genres, list)
        and len(genres) >= SUSPICIOUS_MANY_GENRES
    ):
        signals.append("many listed genres")

    # Signal 4: Relatively small review count.
    total_reviews = reviews.get("total_reviews", 0)

    if total_reviews < SUSPICIOUS_LOW_REVIEW_COUNT:
        signals.append("low review count")

    # Signal 5: Positive rating below the configured threshold.
    positive_percentage = reviews.get("positive_percentage")

    if (
        positive_percentage is not None
        and positive_percentage < SUSPICIOUS_LOW_POSITIVE_PERCENT
    ):
        signals.append("relatively low positive rating")

    if len(signals) >= SUSPICIOUS_MIN_SIGNALS:
        print(
            f"SKIPPED: Suspicious game: {deal.get('title')} "
            f"({len(signals)} signals: {', '.join(signals)})"
        )
        return True

    return False


# -------------------------
# Filter new deals using Steam data
# -------------------------

def filter_new_deals(new_deals):

    eligible_deals = []
    review_api_checks = 0
    review_api_failures = 0

    for item in new_deals:

        deal = item["deal"]
        url = deal["deal"]["url"]

        if is_special_edition(deal["title"]):
            print(f"SKIPPED: Special edition: {deal['title']}")
            continue

        metadata = get_steam_metadata(url)

        if not metadata:
            print(f"SKIPPED: Could not get Steam data: {deal['title']}")
            continue

        if metadata.get("type") != "game":
            print(
                f"SKIPPED: Not a full game: "
                f"{deal['title']} ({metadata.get('type')})"
            )
            continue

        if metadata.get("early_access"):
            print(
                f"SKIPPED: Early Access game: {deal['title']}"
            )
            continue

        if not metadata.get("english_supported"):
            print(
                f"SKIPPED: No English language support listed: "
                f"{deal['title']}"
            )
            continue

        # Check reviews only after all other filters.
        review_api_checks += 1
        reviews = get_steam_reviews(metadata.get("app_id"))

        if reviews is None:
            review_api_failures += 1
            print(
                f"SKIPPED: Steam review data unavailable: "
                f"{deal['title']}"
            )
            continue

        total_reviews = reviews.get("total_reviews", 0)
        positive_percentage = reviews.get("positive_percentage")

        if total_reviews < MIN_STEAM_REVIEWS:
            print(
                f"SKIPPED: Too few Steam reviews "
                f"({total_reviews}): {deal['title']}"
            )
            continue

        if (
            positive_percentage is None
            or positive_percentage < MIN_STEAM_POSITIVE_PERCENT
        ):
            print(
                f"SKIPPED: Low positive Steam rating "
                f"({positive_percentage}%): {deal['title']}"
            )
            continue

        if is_suspicious_game(deal, metadata, reviews):
            continue

        metadata["review_score_desc"] = reviews.get("review_score_desc")
        metadata["total_reviews"] = total_reviews
        metadata["positive_percentage"] = positive_percentage

        item["steam_metadata"] = metadata
        eligible_deals.append(item)

    print(
        f"Eligible games with English subtitles: "
        f"{len(eligible_deals)}"
    )

    if review_api_failures:
        print(
            f"::warning::Steam review data unavailable for "
            f"{review_api_failures} of {review_api_checks} candidates. "
            "Affected games were skipped."
        )

    return eligible_deals
