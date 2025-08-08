import streamlit as st
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
from langchain_openai import OpenAI
from langchain.prompts import PromptTemplate
import docx
import PyPDF2

load_dotenv()
llm = OpenAI(model="gpt-3.5-turbo-instruct")

def extract_text_from_pdf(uploaded_file):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        return "".join([page.extract_text() or "" for page in reader.pages])
    except:
        return ""

def extract_text_from_docx(uploaded_file):
    try:
        doc = docx.Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except:
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

class ResumeJobInput(BaseModel):
    resume: str
    job_description: str

# -------------------
st.set_page_config(page_title="📝 Resume Scorer")
st.title("📝 Resume Scorer")

# Check for job selection in session state
if "selected_job" not in st.session_state:
    st.error("No job selected. Please go back to the homepage and choose a job.")
    st.page_link("app.py", label="🔙 Go to Home")
    st.stop()

job = st.session_state.selected_job
st.markdown(f"### 📌 Scoring for: **{job.get('title', 'N/A')}** at **{job.get('company', {}).get('display_name', 'Unknown')}**")
st.markdown(f"[🔗 View Full Job Posting]({job.get('redirect_url', '#')})")
st.write("---")

# Resume input
resume_input_type = st.selectbox("Resume Input Method", ["Upload File", "Paste Text"])
resume_text = ""
if resume_input_type == "Upload File":
    resume_file = st.file_uploader("Upload your resume (.txt, .pdf, .docx)", type=["txt", "pdf", "docx"])
    if resume_file:
        resume_text = read_uploaded_file(resume_file)
else:
    resume_text = st.text_area("Paste your resume text here")

# JD Input
jd_input_type = st.selectbox("Job Description Input Method", ["Use This Job", "Upload File", "Paste Text"])
jd_text = ""
if jd_input_type == "Use This Job":
    jd_text = job.get('description', '')
elif jd_input_type == "Upload File":
    jd_file = st.file_uploader("Upload the job description (.txt, .pdf, .docx)", type=["txt", "pdf", "docx"])
    if jd_file:
        jd_text = read_uploaded_file(jd_file)
else:
    jd_text = st.text_area("Paste the job description here")

# Submit
if st.button("🚀 Generate Feedback"):
    if not resume_text.strip() or not jd_text.strip():
        st.error("❌ Please provide both resume and job description.")
    else:
        try:
            input_data = ResumeJobInput(resume=resume_text, job_description=jd_text)

            prompt_template = """
            You are a career advisor. Evaluate how well the resume matches the job description.
            Give a score from 1 to 10 and provide 3–5 suggestions to improve the resume.

            Resume:
            {resume}

            Job Description:
            {job_description}

            Respond in this format:

            Score: <number>
            Suggestions:
            - ...
            - ...
            """
            prompt = PromptTemplate.from_template(prompt_template)
            final_prompt = prompt.format(resume=resume_text, job_description=jd_text)

            with st.spinner("Analyzing your resume..."):
                response = llm.invoke(final_prompt)

            st.subheader("📊 Results")
            st.write(response)

        except ValidationError as ve:
            st.error(f"⚠️ Input validation failed: {ve}")
        except Exception as e:
            st.error(f"⚠️ Something went wrong: {e}")
