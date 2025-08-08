import os
import re
import textwrap
import base64
from pathlib import Path

import requests
import streamlit as st
from pydantic import BaseModel, ValidationError


try:
    import docx
except Exception:
    docx = None
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    from langchain_openai import OpenAI
    from langchain.prompts import PromptTemplate
except Exception:
    OpenAI = None
    PromptTemplate = None

from adzuna_api import fetch_jobs

# -------------------- Secrets / Keys --------------------
# Prefer Streamlit secrets on Cloud, fall back to environment locally
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
if OPENAI_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_KEY

# LangChain/OpenAI LLM (optional if you use the scorer)
LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-instruct")
llm = OpenAI(model=LLM_MODEL) if OpenAI else None

# -------------------- Page Config --------------------
st.set_page_config(
    page_title="Applify",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------- THEME / CSS --------------------
st.markdown("""
<style>
:root{
  --card-bg:#ffffff;
  --border:#e6e6e6;
  --muted:#64748b;
  --chip-cyan:#ecfeff;
  --chip-cyan-text:#0e7490;
  --chip-purple:#eef2ff;
  --chip-purple-text:#3730a3;
}

/* App background */
html, body, .block-container { background: #f8fafc !important; }

/* Hide Streamlit's built-in multipage nav ("app", "Resume Scorer", etc.) */
[data-testid="stSidebarNav"] { display:none !important; }

/* Fixed sidebar with cyan ↔ purple gradient */
[data-testid="stSidebar"]{
  background: linear-gradient(180deg, #ecfeff 0%, #eef2ff 100%) !important;
  border-right: 1px solid #e6e6e6;
}
[data-testid="stSidebar"] * { color:#0f172a !important; }

/* Bump top padding so content clears the toolbar and logo isn't clipped */
.block-container { padding-top: 2.75rem !important; }

/* Logo container */
.brand-logo { display:flex; justify-content:center; margin: 28px 0 8px; }
.brand-title { text-align:center; font-size:1.55rem; font-weight:800; margin-top:4px; }

/* Job card */
.job-card {
  border:1px solid var(--border);
  background: var(--card-bg);
  border-radius: 16px;
  padding: 18px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(2,6,23,.05);
}
.job-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.job-title { margin:0; font-size: 1.3rem; }

/* Apply button */
.apply-btn {
  display:inline-block;
  padding: 10px 24px;
  border-radius: 12px;
  text-decoration: none;
  font-weight: 700;
  font-size: 0.98rem;
  background: linear-gradient(135deg, #00c6ff, #0072ff);
  color: #fff !important;
  box-shadow: 0 6px 18px rgba(0, 114, 255, 0.28);
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}
.apply-btn:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(0, 114, 255, 0.36); }
.right { display:flex; justify-content:flex-end; align-items:flex-start; }

/* Chips */
.badges { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.badge {
  display:inline-flex; align-items:center; gap:8px; padding:8px 14px;
  border-radius: 999px; font-weight:700; font-size:.85rem;
}
.badge.cyan { background: var(--chip-cyan); color: var(--chip-cyan-text); }
.badge.purple { background: var(--chip-purple); color: var(--chip-purple-text); }

/* Dividers & text */
.hr { height: 1px; background: var(--border); margin:14px 0; }
.desc { line-height: 1.65; color:#0f172a; font-size: 1.02rem; }
</style>
""", unsafe_allow_html=True)

# -------------------- Logo (Applify) --------------------
logo_path = Path(__file__).parent / "applify_logo.png"
if logo_path.exists():
    b64 = base64.b64encode(logo_path.read_bytes()).decode("utf-8")
    st.markdown(
        f"<div class='brand-logo'><img src='data:image/png;base64,{b64}' alt='Applify' width='160'></div>",
        unsafe_allow_html=True,
    )
st.markdown("<div class='brand-title'>Applify — Find roles. Apply smarter.</div>", unsafe_allow_html=True)

# -------------------- Helpers --------------------
def extract_text_from_pdf(uploaded_file):
    if not PyPDF2:
        return ""
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        return "".join([page.extract_text() or "" for page in reader.pages])
    except Exception:
        return ""

def extract_text_from_docx(uploaded_file):
    if not docx:
        return ""
    try:
        doc = docx.Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception:
        return ""

def read_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return ""
    file_type = uploaded_file.name.lower()
    if file_type.endswith(".pdf"):
        return extract_text_from_pdf(uploaded_file)
    elif file_type.endswith(".docx"):
        return extract_text_from_docx(uploaded_file)
    elif file_type.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")
    else:
        return ""

def job_remote_label(job) -> str:
    if job.get("remote") is True:
        return "Remote"
    desc = (job.get("description") or "").lower()
    title = (job.get("title") or "").lower()
    if any(k in desc or k in title for k in ["remote", "work from home", "wfh", "hybrid"]):
        return "Remote / Hybrid"
    return "On-site"

def split_description(text: str, limit: int = 1200):
    """Return (preview_with_ellipsis, remainder) split at a word boundary."""
    if not text:
        return "", ""
    raw = re.sub(r"\s+", " ", text).strip()
    if len(raw) <= limit:
        return raw, ""
    cut = raw.rfind(" ", 0, limit)
    if cut == -1:
        cut = limit
    preview = raw[:cut].rstrip()
    remainder = raw[cut:].lstrip()
    return preview + "…", remainder

def try_fetch_full_text(url: str) -> str:
    """Best-effort fetch of full JD from redirect_url (optional; needs beautifulsoup4)."""
    if not url:
        return ""
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return ""
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": "Applify/1.0"})
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []
        for tag in soup.find_all(["article", "section", "div"]):
            text = " ".join(p.get_text(" ", strip=True) for p in tag.find_all("p"))
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 400:
                candidates.append(text)
        if candidates:
            return max(candidates, key=len)[:20000]
        all_p = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        return re.sub(r"\s+", " ", all_p).strip()
    except Exception:
        return ""

def normalize_experience(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["intern", "graduate", "junior", "entry"]): return "entry"
    if any(k in t for k in ["mid", "intermediate", "ii", "2-4", "2+", "3+", "associate"]): return "mid"
    if any(k in t for k in ["senior", "sr.", "sr ", "iii", "lead", "staff", "5+", "6+"]): return "senior"
    if "director" in t: return "director"
    if any(k in t for k in ["vp", "vice president", "executive", "head of"]): return "executive"
    return "any"

def format_posted_date(created: str) -> str:
    if not created:
        return "Job Posted on —"
    date_only = created.split("T")[0] if "T" in created else created[:10]
    return f"Job Posted on {date_only}"

class ResumeJobInput(BaseModel):
    resume: str
    job_description: str

# -------------------- State --------------------
if "jobs" not in st.session_state: st.session_state.jobs = []
if "selected_job_index" not in st.session_state: st.session_state.selected_job_index = None
if "desc_open" not in st.session_state: st.session_state.desc_open = {}
if "current_page" not in st.session_state: st.session_state.current_page = 1
if "filters" not in st.session_state: st.session_state.filters = None  # remember filters for paging

def _fetch_with_page(page: int):
    f = st.session_state.filters
    if not f:
        return
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

# -------------------- Sidebar Filters --------------------
with st.sidebar:
    st.subheader("Filters")

    query = st.text_input("Job title / keywords", value="Data Analyst", key="filter_query")
    location = st.text_input("Location (city/state/country)", value="Texas", key="filter_location")

    # Country full names -> codes
    country_map = {
        "United States": "us",
        "United Kingdom": "gb",
        "Canada": "ca",
        "Australia": "au",
        "India": "in",
    }
    country_name = st.selectbox("Country", list(country_map.keys()), index=0, key="filter_country_name")
    country = country_map[country_name]

    col1, col2 = st.columns(2)
    with col1:
        results_per_page = st.selectbox("Results per page", [10, 20, 30, 50], index=0, key="filter_rpp")
    with col2:
        sort_by = st.selectbox("Sort by", ["relevance", "date"], index=0, key="filter_sort")

    salary_min, salary_max = st.slider("Salary range (USD)", 0, 300_000, (0, 0), step=5_000, key="filter_salary")
    category = st.text_input("Category (Adzuna slug, e.g. it-jobs)", value="", key="filter_category")
    distance = st.number_input("Distance (miles)", min_value=0, value=0, step=5, key="filter_distance")
    remote_filter = st.selectbox("Remote", ["Any", "Remote only", "On-site only"], key="filter_remote")

    experience_level = st.selectbox(
        "Experience Level",
        ["Any", "Entry level", "Mid level", "Senior level", "Director", "Executive"],
        key="filter_experience"
    )

    if st.button("🔎 Search Jobs", use_container_width=True, key="filter_search_btn"):
        remote_param = None
        if remote_filter == "Remote only":
            remote_param = True
        elif remote_filter == "On-site only":
            remote_param = False

        st.session_state.filters = {
            "query": query,
            "location": location,
            "results_per_page": results_per_page,
            "country": country,
            "sort_by": sort_by,
            "salary_min": salary_min if salary_min and salary_min > 0 else None,
            "salary_max": salary_max if salary_max and salary_max > 0 else None,
            "category": category or None,
            "remote_param": remote_param,
            "distance": distance if distance and distance > 0 else None,
            "country_name": country_name,
            "remote_filter": remote_filter,
            "experience_level": experience_level,
        }
        st.session_state.current_page = 1
        _fetch_with_page(1)

# -------------------- Results --------------------
jobs = st.session_state.jobs
filters = st.session_state.filters
country_name = filters["country_name"] if filters else "—"
sort_by = filters["sort_by"] if filters else "relevance"
remote_filter = filters["remote_filter"] if filters else "Any"
experience_level = filters["experience_level"] if filters else "Any"
salary_min = filters["salary_min"] if filters else 0
salary_max = filters["salary_max"] if filters else 0

if not jobs:
    st.info("Use the filters on the left and click **Search Jobs**.")
    st.stop()

def client_side_filter(job) -> bool:
    # Remote
    if remote_filter != "Any":
        label = job_remote_label(job)
        if remote_filter == "Remote only" and label == "On-site":
            return False
        if remote_filter == "On-site only" and label.startswith("Remote"):
            return False
    # Salary overlap check
    smin_job = job.get("salary_min")
    smax_job = job.get("salary_max")
    if salary_min and salary_min > 0 and smax_job not in (None, 0):
        if smax_job < salary_min:
            return False
    if salary_max and salary_max > 0 and smin_job not in (None, 0):
        if smin_job > salary_max:
            return False
    # Experience
    if experience_level != "Any":
        level_map = {
            "Entry level": "entry",
            "Mid level": "mid",
            "Senior level": "senior",
            "Director": "director",
            "Executive": "executive",
        }
        desired = level_map[experience_level]
        title = (job.get("title") or "")
        exp_field = (job.get("experience") or "")
        combined = f"{title} {exp_field}".lower()
        def norm_exp(t: str) -> str:
            if any(k in t for k in ["intern", "graduate", "junior", "entry"]): return "entry"
            if any(k in t for k in ["mid", "intermediate", "ii", "2-4", "2+", "3+", "associate"]): return "mid"
            if any(k in t for k in ["senior", "sr.", "sr ", "iii", "lead", "staff", "5+", "6+"]): return "senior"
            if "director" in t: return "director"
            if any(k in t for k in ["vp", "vice president", "executive", "head of"]): return "executive"
            return "any"
        if norm_exp(combined) not in (desired, "any"):
            return False
    return True

jobs_filtered = [j for j in jobs if client_side_filter(j)]

# ---------- Pagination (top) ----------
col_prev, col_page, col_next = st.columns([0.2, 0.6, 0.2])
with col_prev:
    if st.button("⬅️ Previous", disabled=st.session_state.current_page <= 1):
        st.session_state.current_page = max(1, st.session_state.current_page - 1)
        _fetch_with_page(st.session_state.current_page)
        st.rerun()
with col_page:
    st.markdown(
        f"<div style='text-align:center; font-weight:700;'>Page {st.session_state.current_page} — "
        f"Showing {len(jobs_filtered)} results • Country: {country_name} • Sort: {sort_by}</div>",
        unsafe_allow_html=True
    )
with col_next:
    if st.button("Next ➡️"):
        st.session_state.current_page += 1
        _fetch_with_page(st.session_state.current_page)
        st.rerun()

# -------------------- Job Cards --------------------
for i, job in enumerate(jobs_filtered):
    location_disp = job.get('location', {}).get('display_name', 'Location not specified')
    company = job.get('company', {}).get('display_name', 'Unknown Company')
    category_disp = job.get('category', {}).get('label', 'N/A')
    contract = (job.get('contract_time') or 'N/A').replace("_", " ").title()
    remote_label = job_remote_label(job)
    created = job.get("created", "")
    posted_str = f"📅 {format_posted_date(created)}"
    url = job.get('redirect_url', '#')
    title = job.get('title', 'No Title')

    # Salary
    salary_str = "—"
    if job.get("salary_min") or job.get("salary_max"):
        smin = job.get("salary_min") or 0
        smax = job.get("salary_max") or 0
        if smin and smax: salary_str = f"${int(smin):,}–${int(smax):,}"
        elif smax:        salary_str = f"Up to ${int(smax):,}"
        elif smin:        salary_str = f"From ${int(smin):,}"

    # Description (optional full fetch if very short)
    full_desc = job.get('description', '') or ''
    if len(full_desc) < 500 and url:
        fetched = try_fetch_full_text(url)
        if len(fetched) > len(full_desc):
            full_desc = fetched

    preview_desc, remainder_desc = split_description(full_desc, limit=1200)

    with st.container():
        st.markdown('<div class="job-card">', unsafe_allow_html=True)

        c_head, c_cta = st.columns([0.78, 0.22])
        with c_head:
            st.markdown(f"""
<div class="job-head">
  <h4 class="job-title">🧑‍💼 {title}</h4>
</div>
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
            st.markdown(
                f'<div class="right"><a class="apply-btn" href="{url}" target="_blank" rel="noopener">Apply</a></div>',
                unsafe_allow_html=True
            )

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        key_open = f"open_{i}"
        is_open = st.session_state.desc_open.get(key_open, False)

        if not is_open:
            st.markdown(f'<div class="desc">{preview_desc}</div>', unsafe_allow_html=True)
            if remainder_desc:
                if st.button("📜 View full job description", key=f"view_{i}"):
                    st.session_state.desc_open[key_open] = True
                    st.rerun()
        else:
            st.markdown(f'<div class="desc">{full_desc}</div>', unsafe_allow_html=True)
            if st.button("Hide description", key=f"hide_{i}"):
                st.session_state.desc_open[key_open] = False
                st.rerun()

        # -------- Resume Scorer (optional; only if OpenAI installed/configured) --------
        if st.button(f"⚙️ Score My Resume for: {title}", key=f"select_btn_{i}"):
            st.session_state.selected_job_index = i

        st.markdown('</div>', unsafe_allow_html=True)

    # Scoring panel
    if st.session_state.selected_job_index == i:
        st.markdown("---")
        st.subheader("📄 Resume Feedback & Scoring")

        c1, c2 = st.columns([1, 1])
        with c1:
            resume_input_type = st.selectbox("Resume Input Method", ["Upload File", "Paste Text"], key=f"resume_input_{i}")
            resume_text = ""
            if resume_input_type == "Upload File":
                resume_file = st.file_uploader("Upload your resume", type=["txt", "pdf", "docx"], key=f"resume_file_{i}")
                if resume_file:
                    # Tiny helper for reading files here
                    ext = (resume_file.name or "").lower()
                    if ext.endswith(".pdf"):
                        resume_text = extract_text_from_pdf(resume_file)
                    elif ext.endswith(".docx"):
                        resume_text = extract_text_from_docx(resume_file)
                    else:
                        resume_text = resume_file.read().decode("utf-8", errors="ignore")
            else:
                resume_text = st.text_area("Paste your resume text here", height=250, key=f"resume_text_{i}")

        with c2:
            st.markdown("**Job Description (from the listing)**")
            jd_text = full_desc
            st.text_area("Preview", jd_text, height=250, key=f"jd_preview_{i}")

        custom_instructions = st.text_area(
            "Anything specific you want the model to focus on? (optional)",
            key=f"adv_instr_{i}"
        )

        if st.button("🚀 Generate Score", key=f"generate_score_{i}"):
            if not llm:
                st.error("OpenAI / LangChain not installed. Add `openai` and `langchain-openai` to requirements, and set OPENAI_API_KEY.")
            elif not resume_text.strip():
                st.error("❌ Please provide your resume.")
            else:
                try:
                    # validate
                    _ = ResumeJobInput(resume=resume_text, job_description=jd_text)
                    # prompt
                    from langchain.prompts import PromptTemplate as _PT  # safe import if available
                    tmpl = _PT.from_template(textwrap.dedent("""
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
                    """).strip())
                    final_prompt = tmpl.format(
                        resume=resume_text,
                        job_description=jd_text,
                        custom=(custom_instructions or "None"),
                    )
                    with st.spinner("Analyzing your resume..."):
                        response = llm.invoke(final_prompt)
                    st.subheader("📊 Match Score & Suggestions")
                    st.write(response)
                except ValidationError as ve:
                    st.error(f"⚠️ Validation failed: {ve}")
                except Exception as e:
                    st.error(f"⚠️ Error: {e}")

# ---------- Pagination (bottom) ----------
col_prev_b, col_page_b, col_next_b = st.columns([0.2, 0.6, 0.2])
with col_prev_b:
    if st.button("⬅️ Previous ", key="prev_bottom", disabled=st.session_state.current_page <= 1):
        st.session_state.current_page = max(1, st.session_state.current_page - 1)
        _fetch_with_page(st.session_state.current_page)
        st.rerun()
with col_page_b:
    st.markdown(
        f"<div style='text-align:center; font-weight:700;'>Page {st.session_state.current_page}</div>",
        unsafe_allow_html=True
    )
with col_next_b:
    if st.button("Next ➡️", key="next_bottom"):
        st.session_state.current_page += 1
        _fetch_with_page(st.session_state.current_page)
        st.rerun()
