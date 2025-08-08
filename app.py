import os
import re
import textwrap
import base64
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
import docx
import PyPDF2

from adzuna_api import fetch_jobs

# ==================== LLM / KEYS ====================
# Load .env only if present and DO NOT override Render env vars.
for p in (Path("/etc/secrets/.env"), Path(".env")):
    if p.exists():
        load_dotenv(p, override=False)

# Prefer Render environment values
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_PROJECT = os.getenv("OPENAI_PROJECT")   # needed for sk-proj-* keys (env var only)
OPENAI_ORG = os.getenv("OPENAI_ORG_ID")       # optional

# Expose env vars for libraries that read from os.environ
if OPENAI_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_KEY
if OPENAI_PROJECT:
    os.environ["OPENAI_PROJECT"] = OPENAI_PROJECT  # relied on by OpenAI SDK; we won't pass it in code
if OPENAI_ORG:
    os.environ["OPENAI_ORG_ID"] = OPENAI_ORG

# Try to import langchain bits; app still works without LLM.
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LANGCHAIN_OK = True
except Exception:
    LANGCHAIN_OK = False
    ChatOpenAI = None
    PromptTemplate = None

LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # safe, current

llm = None
if LANGCHAIN_OK and OPENAI_KEY:
    try:
        # NOTE: do NOT pass project= here (some versions don't support it).
        # The OpenAI SDK will read OPENAI_PROJECT from env if you're using sk-proj keys.
        llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=0,
            openai_api_key=OPENAI_KEY,
            organization=OPENAI_ORG,  # fine if None
        )
    except Exception as e:
        llm = None
        st.error(f"OpenAI init failed: {e}")

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="Applify",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== THEME / CSS ====================
st.markdown("""
<style>
:root{
  --card-bg:#ffffff; --border:#e6e6e6; --muted:#64748b;
  --chip-cyan:#ecfeff; --chip-cyan-text:#0e7490;
  --chip-purple:#eef2ff; --chip-purple-text:#3730a3;
}
html, body, .block-container { background:#f8fafc !important; }
[data-testid="stSidebarNav"]{ display:none !important; }
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#ecfeff 0%,#eef2ff 100%) !important;
  border-right:1px solid #e6e6e6;
}
[data-testid="stSidebar"] * { color:#0f172a !important; }
h1,h2,h3,h4{ color:#0f172a; }
.brand-logo{ display:flex; justify-content:center; margin:4px 0 8px; }
.brand-title{ text-align:center; font-size:1.6rem; font-weight:800; margin-top:4px; }
.job-card{ border:1px solid var(--border); background:var(--card-bg); border-radius:16px; padding:18px; margin-bottom:16px; box-shadow:0 1px 2px rgba(2,6,23,.05); }
.job-head{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.job-title{ margin:0; font-size:1.3rem; }
.apply-btn{ display:inline-block; padding:10px 24px; border-radius:12px; text-decoration:none; font-weight:700; font-size:.98rem;
  background:linear-gradient(135deg,#00c6ff,#0072ff); color:#fff !important; box-shadow:0 6px 18px rgba(0,114,255,.28);
  transition:transform .1s ease, box-shadow .1s ease; }
.apply-btn:hover{ transform:translateY(-1px); box-shadow:0 10px 22px rgba(0,114,255,.36); }
.right{ display:flex; justify-content:flex-end; align-items:flex-start; }
.badges{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.badge{ display:inline-flex; align-items:center; gap:8px; padding:8px 14px; border-radius:999px; font-weight:700; font-size:.85rem; }
.badge.cyan{ background:var(--chip-cyan); color:var(--chip-cyan-text); }
.badge.purple{ background:var(--chip-purple); color:var(--chip-purple-text); }
.hr{ height:1px; background:var(--border); margin:14px 0; }
.desc{ line-height:1.65; color:#0f172a; font-size:1.02rem; }
.subtle{ color:var(--muted); }
.block-container{ padding-top:.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ==================== Logo ====================
logo_path = Path(__file__).parent / "applify_logo.png"
if logo_path.exists():
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode("utf-8")
    st.markdown(
        f"""<div class="brand-logo"><img src="data:image/png;base64,{logo_b64}" alt="Applify" width="160"></div>""",
        unsafe_allow_html=True,
    )
else:
    st.warning("Logo file not found. Add 'applify_logo.png' next to app.py to show the logo.")
st.markdown('<div class="brand-title">Applify — Find roles. Apply smarter.</div>', unsafe_allow_html=True)

# ==================== Helpers ====================
def extract_text_from_pdf(uploaded_file):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        return "".join([page.extract_text() or "" for page in reader.pages])
    except Exception:
        return ""

def extract_text_from_docx(uploaded_file):
    try:
        doc = docx.Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception:
        return ""

def read_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return ""
    file_type = uploaded_file.name.lower()
    if file_type.endswith(".pdf"): return extract_text_from_pdf(uploaded_file)
    if file_type.endswith(".docx"): return extract_text_from_docx(uploaded_file)
    if file_type.endswith(".txt"):  return uploaded_file.read().decode("utf-8", errors="ignore")
    return ""

def job_remote_label(job) -> str:
    if job.get("remote") is True:
        return "Remote"
    desc = (job.get("description") or "").lower()
    title = (job.get("title") or "").lower()
    if any(k in desc or k in title for k in ["remote","work from home","wfh","hybrid"]):
        return "Remote / Hybrid"
    return "On-site"

def split_description(text: str, limit: int = 1200):
    if not text: return "", ""
    raw = re.sub(r"\s+", " ", text).strip()
    if len(raw) <= limit: return raw, ""
    cut = raw.rfind(" ", 0, limit)
    if cut == -1: cut = limit
    return raw[:cut].rstrip() + "…", raw[cut:].lstrip()

def try_fetch_full_text(url: str) -> str:
    if not url: return ""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return ""
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent":"Applify/1.0"})
        if resp.status_code != 200: return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []
        for tag in soup.find_all(["article","section","div"]):
            text = " ".join(p.get_text(" ", strip=True) for p in tag.find_all("p"))
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 400: candidates.append(text)
        if candidates: return max(candidates, key=len)[:20000]
        all_p = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        return re.sub(r"\s+", " ", all_p).strip()
    except Exception:
        return ""

def format_posted_date(created: str) -> str:
    if not created: return "Job Posted on —"
    date_only = created.split("T")[0] if "T" in created else created[:10]
    return f"Job Posted on {date_only}"

class ResumeJobInput(BaseModel):
    resume: str
    job_description: str

# ==================== STATE ====================
if "jobs" not in st.session_state: st.session_state.jobs = []
if "selected_job_index" not in st.session_state: st.session_state.selected_job_index = None
if "desc_open" not in st.session_state: st.session_state.desc_open = {}
if "current_page" not in st.session_state: st.session_state.current_page = 1
if "filters" not in st.session_state: st.session_state.filters = None

def _fetch_with_page(page: int):
    f = st.session_state.filters
    if not f: return
    with st.spinner("Loading jobs..."):
        st.session_state.jobs = fetch_jobs(
            query=f["query"],
            location=f["location"],
            results_limit=f["results_per_page"],
            page=page,
            country=f["country"],
            sort_by=f["sort_by"],
            salary_min=f["salary_min"],
            salary_max=f["salary_max"],
            category=f["category"],
            remote=f["remote_param"],
            distance=f["distance"],
        )
        st.session_state.desc_open = {}

# ==================== FILTERS (SIDEBAR) ====================
with st.sidebar:
    st.subheader("Filters")
    query = st.text_input("Job title / keywords", value="Data Analyst", key="filter_query")
    location = st.text_input("Location (city/state/country)", value="Texas", key="filter_location")

    country_map = {"United States":"us","United Kingdom":"gb","Canada":"ca","Australia":"au","India":"in"}
    country_name = st.selectbox("Country", list(country_map.keys()), index=0, key="filter_country_name")
    country = country_map[country_name]

    col1, col2 = st.columns(2)
    with col1:
        results_per_page = st.selectbox("Results per page", [10,20,30,50], index=0, key="filter_rpp")
    with col2:
        sort_by = st.selectbox("Sort by", ["relevance","date"], index=0, key="filter_sort")

    salary_min, salary_max = st.slider("Salary range (USD)", 0, 300_000, (0, 0), step=5_000, key="filter_salary")
    category = st.text_input("Category (Adzuna slug, e.g. it-jobs)", value="", key="filter_category")
    distance = st.number_input("Distance (miles)", min_value=0, value=0, step=5, key="filter_distance")
    remote_filter = st.selectbox("Remote", ["Any","Remote only","On-site only"], key="filter_remote")

    experience_level = st.selectbox(
        "Experience Level",
        ["Any","Entry level","Mid level","Senior level","Director","Executive"],
        key="filter_experience"
    )

    if st.button("🔎 Search Jobs", use_container_width=True, key="filter_search_btn"):
        remote_param = None
        if remote_filter == "Remote only": remote_param = True
        elif remote_filter == "On-site only": remote_param = False

        st.session_state.filters = {
            "query": query, "location": location, "results_per_page": results_per_page,
            "country": country, "sort_by": sort_by,
            "salary_min": salary_min if salary_min > 0 else None,
            "salary_max": salary_max if salary_max > 0 else None,
            "category": category or None, "remote_param": remote_param,
            "distance": distance if distance > 0 else None,
            "country_name": country_name, "remote_filter": remote_filter,
            "experience_level": experience_level,
        }
        st.session_state.current_page = 1
        _fetch_with_page(1)

# ==================== RESULTS ====================
jobs = st.session_state.jobs
filters = st.session_state.filters
country_name = filters["country_name"] if filters else "—"
sort_by = filters["sort_by"] if filters else "relevance"

if not jobs:
    st.info("Use the filters on the left and click **Search Jobs**.")
else:
    # pagination top
    col_prev, col_page, col_next = st.columns([0.2, 0.6, 0.2])
    with col_prev:
        if st.button("⬅️ Previous", disabled=st.session_state.current_page <= 1):
            st.session_state.current_page = max(1, st.session_state.current_page - 1)
            _fetch_with_page(st.session_state.current_page)
            st.rerun()
    with col_page:
        st.markdown(
            f"<div style='text-align:center; font-weight:700;'>Page {st.session_state.current_page} • Country: {country_name} • Sort: {sort_by}</div>",
            unsafe_allow_html=True
        )
    with col_next:
        if st.button("Next ➡️"):
            st.session_state.current_page += 1
            _fetch_with_page(st.session_state.current_page)
            st.rerun()

    # job cards
    for i, job in enumerate(jobs):
        location_disp = job.get('location', {}).get('display_name', 'Location not specified')
        company = job.get('company', {}).get('display_name', 'Unknown Company')
        category_disp = job.get('category', {}).get('label', 'N/A')
        contract = (job.get('contract_time') or 'N/A').replace("_", " ").title()
        remote_label = job_remote_label(job)
        posted_str = f"📅 {format_posted_date(job.get('created',''))}"
        url = job.get('redirect_url', '#')
        title = job.get('title', 'No Title')

        salary_str = "—"
        if job.get("salary_min") or job.get("salary_max"):
            smin = job.get("salary_min") or 0
            smax = job.get("salary_max") or 0
            if smin and smax: salary_str = f"${int(smin):,}–${int(smax):,}"
            elif smax:        salary_str = f"Up to ${int(smax):,}"
            elif smin:        salary_str = f"From ${int(smin):,}"

        full_desc = job.get('description', '') or ''
        if len(full_desc) < 500 and url:
            fetched = try_fetch_full_text(url)
            if len(fetched) > len(full_desc): full_desc = fetched

        preview_desc, remainder_desc = split_description(full_desc, limit=1200)

        with st.container():
            st.markdown('<div class="job-card">', unsafe_allow_html=True)
            c_head, c_cta = st.columns([0.78, 0.22])
            with c_head:
                st.markdown(f"""
<div class="job-head"><h4 class="job-title">🧑‍💼 {title}</h4></div>
<p style="margin:4px 0 0 0;"><strong>{company}</strong> · {category_disp}</p>
<div class="badges">
  <span class="badge cyan">📍 {location_disp}</span>
  <span class="badge purple">🕒 {contract}</span>
  <span class="badge cyan">🏡 {remote_label}</span>
  <span class="badge purple">{posted_str}</span>
  <span class="badge cyan">💰 {salary_str}</span>
</div>
""", unsafe_allow_html=True)
            with c_cta:
                st.markdown(f'<div class="right"><a class="apply-btn" href="{url}" target="_blank" rel="noopener">Apply</a></div>', unsafe_allow_html=True)

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            key_open = f"open_{i}"
            is_open = st.session_state.desc_open.get(key_open, False)
            if not is_open:
                st.markdown(f'<div class="desc">{preview_desc}</div>', unsafe_allow_html=True)
                if remainder_desc and st.button("📜 View full job description", key=f"view_{i}"):
                    st.session_state.desc_open[key_open] = True
                    st.rerun()
            else:
                st.markdown(f'<div class="desc">{full_desc}</div>', unsafe_allow_html=True)
                if st.button("Hide description", key=f"hide_{i}"):
                    st.session_state.desc_open[key_open] = False
                    st.rerun()

            if st.button(f"⚙️ Score My Resume for: {title}", key=f"select_btn_{i}"):
                st.session_state.selected_job_index = i

            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.selected_job_index == i:
            st.markdown("---")
            st.subheader("📄 Resume Feedback & Scoring")

            c1, c2 = st.columns([1, 1])
            with c1:
                resume_input_type = st.selectbox("Resume Input Method", ["Upload File", "Paste Text"], key=f"resume_input_{i}")
                resume_text = ""
                if resume_input_type == "Upload File":
                    resume_file = st.file_uploader("Upload your resume", type=["txt","pdf","docx"], key=f"resume_file_{i}")
                    if resume_file:
                        resume_text = read_uploaded_file(resume_file)
                else:
                    resume_text = st.text_area("Paste your resume text here", height=250, key=f"resume_text_{i}")

            with c2:
                st.markdown("**Job Description (from the listing)**")
                jd_text = full_desc
                st.text_area("Preview", jd_text, height=250, key=f"jd_preview_{i}")

            with st.expander("Advanced (optional)"):
                custom_instructions = st.text_area(
                    "Anything specific you want the model to focus on? (e.g., SQL projects, metrics)",
                    key=f"adv_instr_{i}"
                )

            if st.button("🚀 Generate Score", key=f"generate_score_{i}"):
                if llm is None:
                    st.error("LLM not initialized. Check OPENAI_API_KEY / OPENAI_PROJECT on Render and packages installed.")
                elif not resume_text.strip():
                    st.error("❌ Please provide your resume.")
                else:
                    try:
                        _ = ResumeJobInput(resume=resume_text, job_description=jd_text)
                        prompt_template = """
You are a strict but helpful career advisor. Evaluate how well the resume matches the job description.
1) Give an overall match score from 1 to 10.
2) List 5 specific, actionable suggestions for improving the resume for THIS job.
3) Identify missing keywords/skills based on the JD.
4) Propose 2-3 quantified bullets the candidate could add, tailored to the JD.

EXTRA NOTES FROM CANDIDATE (optional):
{custom}

RESUME:
{resume}

JOB DESCRIPTION:
{job_description}

Respond in this exact format:

Score: <number>/10

Suggestions:
- ...

Missing Keywords:
- ...

New Bullet Ideas:
- ...
""".strip()
                        prompt = PromptTemplate.from_template(prompt_template)
                        final_prompt = prompt.format(
                            resume=resume_text,
                            job_description=jd_text,
                            custom=(custom_instructions or "None"),
                        )
                        with st.spinner("Analyzing your resume..."):
                            resp = llm.invoke(final_prompt)
                        st.subheader("📊 Match Score & Suggestions")
                        st.write(resp.content)  # ChatOpenAI returns an AIMessage; use .content
                    except ValidationError as ve:
                        st.error(f"⚠️ Validation failed: {ve}")
                    except Exception as e:
                        st.error(f"⚠️ Error: {e}")

    # pagination bottom
    col_prev_b, col_page_b, col_next_b = st.columns([0.2, 0.6, 0.2])
    with col_prev_b:
        if st.button("⬅️ Previous ", key="prev_bottom", disabled=st.session_state.current_page <= 1):
            st.session_state.current_page = max(1, st.session_state.current_page - 1)
            _fetch_with_page(st.session_state.current_page)
            st.rerun()
    with col_page_b:
        st.markdown(f"<div style='text-align:center; font-weight:700;'>Page {st.session_state.current_page}</div>", unsafe_allow_html=True)
    with col_next_b:
        if st.button("Next ➡️", key="next_bottom"):
            st.session_state.current_page += 1
            _fetch_with_page(st.session_state.current_page)
            st.rerun()
