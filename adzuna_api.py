# adzuna_api.py
import os, requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

BASE_URL_TMPL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

def _clamp(n:int, lo:int, hi:int)->int: return max(lo, min(hi, n))

def fetch_jobs(
    query: str = "",
    location: str = "",
    results_limit: int = 10,
    page: int = 1,
    country: str = "us",
    sort_by: str = "relevance",        # "relevance" | "date"
    salary_min: int | None = None,
    salary_max: int | None = None,
    category: str | None = None,
    distance: int | None = None,
    **kwargs,                          # absorb any extras safely
):
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    country = (country or "us").lower()
    page = _clamp(int(page or 1), 1, 100)
    results_limit = _clamp(int(results_limit or 10), 1, 50)

    url = BASE_URL_TMPL.format(country=country, page=page)
    params: dict[str, object] = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_limit,
        "what": (query or "").strip() or None,
        "where": (location or "").strip() or None,
        "sort_by": sort_by if sort_by in ("relevance", "date") else "relevance",
    }
    if salary_min: params["salary_min"] = int(salary_min)
    if salary_max: params["salary_max"] = int(salary_max)
    if category:   params["category"]   = category
    if distance:   params["distance"]   = int(distance)

    params = {k: v for k, v in params.items() if v not in (None, "", 0)}

    try:
        r = requests.get(url, params=params, headers={"User-Agent":"Applify/1.0"}, timeout=20)
        r.raise_for_status()
        return r.json().get("results", []) or []
    except requests.RequestException:
        return []
