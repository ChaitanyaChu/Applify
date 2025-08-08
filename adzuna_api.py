# adzuna_api.py
import os
import requests
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
from pathlib import Path

# Load .env for local dev only; DO NOT override Render env vars.
for p in (Path("/etc/secrets/.env"), Path(".env")):
    if p.exists():
        load_dotenv(p, override=False)

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

BASE_URL_TEMPLATE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

def _build_params(
    query: str,
    location: str,
    results_limit: int,
    sort_by: str,
    salary_min: Optional[int],
    salary_max: Optional[int],
    category: Optional[str],
    remote: Optional[bool],
    distance: Optional[int],
) -> Dict[str, Any]:
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        raise RuntimeError("Missing ADZUNA_APP_ID or ADZUNA_APP_KEY in environment.")

    params: Dict[str, Any] = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_limit,
        "what": query or "",
        "where": location or "",
        "sort_by": sort_by or "relevance",  # "relevance" or "date"
    }
    if salary_min is not None:
        params["salary_min"] = salary_min
    if salary_max is not None:
        params["salary_max"] = salary_max
    if category:
        params["category"] = category           # e.g., "it-jobs"
    if distance is not None and distance > 0:
        params["distance"] = distance
    if remote is not None:
        params["remote"] = str(remote).lower()  # not supported everywhere; harmless

    return params

def fetch_jobs(
    query: str = "data analyst",
    location: str = "Texas",
    *,
    results_limit: int = 10,
    page: int = 1,
    country: str = "us",
    sort_by: str = "relevance",
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    category: Optional[str] = None,
    remote: Optional[bool] = None,
    distance: Optional[int] = None,
    return_debug: bool = False,
) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Fetch jobs from Adzuna. If return_debug=True, returns (jobs, debug_meta)
    where debug_meta includes url, params, status_code, and any error text.
    """
    url = BASE_URL_TEMPLATE.format(country=country.lower(), page=max(1, int(page)))
    params = _build_params(
        query=query,
        location=location,
        results_limit=results_limit,
        sort_by=sort_by,
        salary_min=salary_min,
        salary_max=salary_max,
        category=category,
        remote=remote,
        distance=distance,
    )
    headers = {
        "Accept": "application/json",
        "User-Agent": "Applify/1.0 (+https://example.local)"
    }

    debug: Dict[str, Any] = {"url": url, "params": params, "status_code": None, "error": None}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        debug["status_code"] = resp.status_code
        resp.raise_for_status()
        data = resp.json() or {}
        jobs = data.get("results", []) or []
        if return_debug:
            return jobs, debug
        return jobs
    except requests.RequestException as e:
        debug["error"] = f"HTTP error: {e}"
    except ValueError as e:
        debug["error"] = f"JSON parse error: {e}"
    except Exception as e:
        debug["error"] = f"Unexpected error: {e}"

    if return_debug:
        return [], debug
    return []
