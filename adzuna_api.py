# adzuna_api.py
import os
import requests

# Load .env locally (Render can use Environment Variables or Secret Files)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

BASE_URL_TMPL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch_jobs(
    query: str = "",
    location: str = "",
    results_limit: int = 10,
    distance: int = 0,
    page: int = 1,
    country: str = "us",
):
    """
    Fetch jobs from Adzuna with a simple set of params to match app.py.

    Args:
        query: Keywords to search for (what)
        location: Location string (where)
        results_limit: results_per_page (1..50)
        distance: radius in miles (0 disables)
        page: page number (1..100)
        country: two-letter Adzuna country code (default 'us')
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    # Clamp values to Adzuna's sane ranges
    try:
        results_limit = max(1, min(int(results_limit or 10), 50))
        page = max(1, min(int(page or 1), 100))
        distance = int(distance or 0)
    except Exception:
        results_limit, page, distance = 10, 1, 0

    url = BASE_URL_TMPL.format(country=(country or "us").lower(), page=page)

    params: dict[str, object] = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_limit,
    }
    if query:
        params["what"] = query
    if location:
        params["where"] = location
    if distance > 0:
        params["distance"] = distance  # miles

    try:
        r = requests.get(url, params=params, headers={"User-Agent": "Applify/1.0"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("results", []) or []
    except requests.RequestException:
        return []
