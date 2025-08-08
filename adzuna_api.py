import requests
import os
from dotenv import load_dotenv

# Load .env variables (works locally, Render will use env vars directly)
load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

BASE_URL = "https://api.adzuna.com/v1/api/jobs"

def fetch_jobs(country="us", query="", location="", results_limit=10, page=1, experience_level=None):
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_limit,
        "what": query,
        "where": location,
        "page": page,
        "content-type": "application/json"
    }

    if experience_level:
        params["experience_level"] = experience_level

    try:
        url = f"{BASE_URL}/{country}/search/1"
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.RequestException:
        return []
