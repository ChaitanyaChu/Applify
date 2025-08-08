import os
import requests

try:
    import streamlit as st  # noqa
except Exception:  # running outside Streamlit
    st = None  # type: ignore


def _get_secret(name: str, default: str | None = None) -> str | None:
    if st and hasattr(st, "secrets") and name in st.secrets:
        return st.secrets[name]
    return os.getenv(name, default)


ADZUNA_APP_ID = _get_secret("ADZUNA_APP_ID")
ADZUNA_APP_KEY = _get_secret("ADZUNA_APP_KEY")

# country + page are path params in Adzuna
BASE_URL_TMPL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch_jobs(
    query: str = "data analyst",
    location: str = "Texas",
    results_limit: int = 10,
    page: int = 1,
    country: str = "us",
    sort_by: str = "relevance",  # relevance | date
    salary_min: int | None = None,
    salary_max: int | None = None,
    category: str | None = None,  # e.g., "it-jobs"
    remote: bool | None = None,   # True, False, or None
    distance: int | None = None,  # miles
):
    """Fetch jobs from Adzuna. Returns a list of job dicts or [] on error."""
    base_url = BASE_URL_TMPL.format(country=country, page=page)

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_limit,
        "what": query,
        "where": location,
        "sort_by": sort_by,
        "content-type": "application/json",
    }
    if salary_min:
        params["salary_min"] = salary_min
    if salary_max:
        params["salary_max"] = salary_max
    if category:
        params["category"] = category
    if distance:
        params["distance"] = distance

    # crude remote filter: include or exclude 'remote' as a required word
    if remote is True:
        params["what_and"] = "remote"
    elif remote is False:
        params["what_and"] = "-remote"

    try:
        resp = requests.get(base_url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except requests.RequestException as e:
        print(f"[Adzuna] API error: {e}")
        return []
