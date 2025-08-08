import os
import requests

# Use Streamlit secrets on Cloud; env vars locally
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # type: ignore


def _get_secret(name: str, default: str | None = None) -> str | None:
    if st and hasattr(st, "secrets") and name in st.secrets:
        return st.secrets[name]
    return os.getenv(name, default)


ADZUNA_APP_ID = _get_secret("ADZUNA_APP_ID")
ADZUNA_APP_KEY = _get_secret("ADZUNA_APP_KEY")

BASE_URL_TMPL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def fetch_jobs(
    query: str = "data analyst",
    location: str = "Texas",
    results_limit: int = 10,
    page: int = 1,
    country: str = "us",
    sort_by: str = "relevance",  # relevance | date
    salary_min: int | None = None,
    salary_max: int | None = None,
    category: str | None = None,  # e.g. "it-jobs"
    distance: int | None = None,  # miles
):
    """
    Spec-compliant Adzuna call. Avoids unsupported/empty params that cause 400s.
    """
    page = _clamp(int(page or 1), 1, 100)
    results_limit = _clamp(int(results_limit or 10), 1, 50)
    country = (country or "us").lower()

    url = BASE_URL_TMPL.format(country=country, page=page)
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_limit,
        "what": (query or "").strip() or None,
        "where": (location or "").strip() or None,
        "sort_by": sort_by if sort_by in ("relevance", "date") else "relevance",
    }
    # Drop empty params
    params = {k: v for k, v in params.items() if v not in (None, "", 0)}

    if salary_min:
        params["salary_min"] = int(salary_min)
    if salary_max:
        params["salary_max"] = int(salary_max)
    if category:
        params["category"] = category
    if distance:
        params["distance"] = int(distance)

    headers = {"User-Agent": "Applify/1.0"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        if r.status_code != 200:
            # Surface helpful diagnostics in logs
            try:
                body = r.json()
            except Exception:
                body = r.text[:400]
            print(f"[Adzuna] {r.status_code} for {r.url} :: {body}")
            r.raise_for_status()
        return r.json().get("results", [])
    except requests.HTTPError as e:
        print(f"[Adzuna] API error: {e}")
        return []
    except requests.RequestException as e:
        print(f"[Adzuna] Network error: {e}")
        return []


def adzuna_ping(country="us"):
    """Tiny debug endpoint to verify creds/endpoint."""
    url = BASE_URL_TMPL.format(country=country, page=1)
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": "engineer",
        "results_per_page": 1,
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        out = {"status": r.status_code, "url": r.url}
        try:
            js = r.json()
            out["count"] = len(js.get("results", []))
            out["message"] = js.get("message") or js.get("error")
        except Exception:
            out["text"] = r.text[:400]
        return out
    except Exception as e:
        return {"status": None, "error": str(e), "url": url}
