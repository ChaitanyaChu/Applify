import os
import requests

# Streamlit may not exist in all contexts; keep optional
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # type: ignore


BASE_URL_TMPL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _get_secret_now(name: str) -> str | None:
    """
    Read a secret at CALL TIME.
    Prefer st.secrets when available; fall back to os.environ.
    """
    if st is not None:
        try:
            return st.secrets.get(name)  # type: ignore[attr-defined]
        except Exception:
            pass
    return os.getenv(name)


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
    Spec-compliant Adzuna call; avoids unsupported/empty params that trigger 400s.
    Reads credentials at call time so hosting environments always work.
    """
    app_id = _get_secret_now("ADZUNA_APP_ID")
    app_key = _get_secret_now("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        if st is not None:
            st.error("Adzuna credentials missing. Set ADZUNA_APP_ID and ADZUNA_APP_KEY.")
        return []

    page = _clamp(int(page or 1), 1, 100)
    results_limit = _clamp(int(results_limit or 10), 1, 50)
    country = (country or "us").lower()

    url = BASE_URL_TMPL.format(country=country, page=page)
    params: dict[str, object] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": results_limit,
        "what": (query or "").strip() or None,
        "where": (location or "").strip() or None,
        "sort_by": sort_by if sort_by in ("relevance", "date") else "relevance",
    }

    # Optional filters
    if salary_min:
        params["salary_min"] = int(salary_min)
    if salary_max:
        params["salary_max"] = int(salary_max)
    if category:
        params["category"] = category
    if distance:
        params["distance"] = int(distance)

    # Drop Nones/empties
    params = {k: v for k, v in params.items() if v not in (None, "", 0)}

    headers = {"User-Agent": "Applify/1.0"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        if r.status_code != 200:
            try:
                body = r.json()
            except Exception:
                body = r.text[:400]
            print(f"[Adzuna] {r.status_code} for {r.url} :: {body}")
            r.raise_for_status()
        js = r.json()
        return js.get("results", []) or []
    except requests.RequestException as e:
        print(f"[Adzuna] error: {e}")
        return []


def build_request(
    query: str,
    location: str,
    results_limit: int,
    page: int,
    country: str,
    sort_by: str,
    salary_min: int | None,
    salary_max: int | None,
    category: str | None,
    distance: int | None,
):
    """
    Return (url, params) exactly as fetch_jobs() would send, without calling the API.
    """
    app_id = _get_secret_now("ADZUNA_APP_ID")
    app_key = _get_secret_now("ADZUNA_APP_KEY")

    page = _clamp(int(page or 1), 1, 100)
    results_limit = _clamp(int(results_limit or 10), 1, 50)
    country = (country or "us").lower()
    url = BASE_URL_TMPL.format(country=country, page=page)
    params: dict[str, object] = {
        "app_id": app_id,
        "app_key": app_key,
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
    return url, params


def adzuna_ping(country="us"):
    """Quick connectivity/credentials check."""
    app_id = _get_secret_now("ADZUNA_APP_ID")
    app_key = _get_secret_now("ADZUNA_APP_KEY")
    url = BASE_URL_TMPL.format(country=(country or "us").lower(), page=1)
    params = {
        "app_id": app_id,
        "app_key": app_key,
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
