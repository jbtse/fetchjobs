import os
import sys
import time
import re
import json
import sqlite3
from datetime import datetime
import pandas as pd
from pypdf import PdfReader
from jobspy import scrape_jobs
import ollama

# -------------------------------------------------------------
# 1. CONFIGURATION
# -------------------------------------------------------------
DB_FILE = "application_tracker.db"
BASE_RESUME_PDF_PATH = "Resume.pdf"
# The script will search for every combination of these roles and locations
SEARCH_ROLES = ["Kotlin Developer", "Backend Engineer", "Software Engineer"]
LOCATIONS = ["Remote", "San Francisco, CA", "San Jose, CA", "San Bruno, CA", "Palo Alto, CA", "Mountain View, CA", "Sunnyvale, CA", "Santa Clara, CA", "Redwood City, CA"]
RESULTS_PER_SEARCH = 10  # Max results to pull per individual search combo

# Priority target keywords for scoring
TARGET_KEYWORDS = [
    "kotlin", "java", "python", "postgresql", "sql", "graphql", "grpc", "jpa", "jdbc", 
    "docker", "maven", "gradle", "chronosphere", "redis", "aes encryption", "rest api", "aws", "git",
    "microservices", "monoservices", "spring boot", "spring", "hibernate", "junit", "kubernetes", "ci/cd",
    "bloomrpc", "node.js", "sdlc", "prometheus", "datadog",
    "code reviews", "unit testing", "integration testing", "platform modernization",
    "legacy migration", "feature flags", "feature ramping", "object oriented programming", "agile", "scrum"  
]
MINIMUM_KEYWORD_MATCHES = 3

# New Filters and Thresholds
MINIMUM_MATCH_SCORE = 50  # Base threshold out of 100

EXCLUDED_SENIORITY = [
    "Staff", "Principal", "Director", "VP", "Vice President", 
    "Head of", "Architect", "Lead", "Manager", "Senior Manager"
]

AVOID_KEYWORDS = [
    "unpaid", "internship", "intern"
]

# Get the folder where the current script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

target_audits_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume_audits")
target_tracker_path = os.path.join(script_dir, "application_tracker.csv")

OUTPUT_AUDIT_FOLDER = target_audits_path
TRACKER_CSV_FILE = target_tracker_path
os.makedirs(OUTPUT_AUDIT_FOLDER, exist_ok=True)

# Form Auto-fill profile
CANDIDATE_INFO = {
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "linkedin": "https://www.linkedin.com/in/"
}

# -------------------------------------------------------------
# 2. SQL DATABASE UTILITIES
# -------------------------------------------------------------
def init_db():
    """Initializes a local relational database to handle structured text safely."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            company TEXT,
            role_title TEXT,
            location TEXT,
            status TEXT,
            match_score INTEGER,
            missing_keywords TEXT,
            suggested_improvements TEXT,
            reasoning TEXT,
            job_url TEXT UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

def load_existing_urls():
    """Reads all tracked URLs natively from SQL to prevent re-scraping."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT job_url FROM job_tracker')
    urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    return urls

def update_tracker(company, title, location, job_url, score, status, missing_kw="", improvements="", reasoning=""):
    """Inserts records reliably into SQL using parameter binding (immune to comma errors)."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO job_tracker 
            (timestamp, company, role_title, location, status, match_score, missing_keywords, suggested_improvements, reasoning, job_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(company or ""),
            str(title or ""),
            str(location or ""),
            status,
            int(score),
            str(missing_kw or ""),
            str(improvements or ""),
            str(reasoning or ""),
            str(job_url or "")
        ))
        conn.commit()
    except Exception as e:
        print(f"  [!] Database log write error: {e}")
    finally:
        conn.close()

# -------------------------------------------------------------
# 3. PDF & TEXT PROCESSORS
# -------------------------------------------------------------
def extract_text_from_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"[!] Error: Resume not found at '{pdf_path}'. Place your PDF here.")
        sys.exit(1)
    try:
        reader = PdfReader(pdf_path)
        pages = [p.extract_text() for p in reader.pages if p.extract_text()]
        text = "\n".join(pages).strip()
        if not text:
            print(f"[!] Error: No readable text found in '{pdf_path}'.")
            sys.exit(1)
        print(f"[✓] Loaded master resume from '{pdf_path}' ({len(reader.pages)} pages).")
        return text
    except Exception as e:
        print(f"[!] Error reading resume PDF: {e}")
        sys.exit(1)

def check_title_exclusions(title):
    title_str = str(title or "")
    for sen in EXCLUDED_SENIORITY:
        if re.search(rf"\b{re.escape(sen)}\b", title_str, re.IGNORECASE):
            return f"Excluded seniority: {sen}"
    return None

def check_negative_keywords(text):
    text_str = str(text or "").lower()
    for bad_kw in AVOID_KEYWORDS:
        if bad_kw.lower() in text_str:
            if f"no {bad_kw}" in text_str or f"not {bad_kw}" in text_str:
                continue
            return f"Avoid keyword: {bad_kw}"
    return None

def audit_resume_and_suggest(job_title, company, job_description, resume_text):
    safe_title = str(job_title or "")
    safe_company = str(company or "")
    safe_desc = str(job_description or "")[:2500] if pd.notna(job_description) else ""

    prompt = f'''You are an expert ATS auditor and technical hiring manager.
Compare the candidate's authentic resume with this target job posting.
DO NOT fabricate experience. Provide an objective score and concrete suggestions.

Return ONLY a valid JSON object matching this schema:
{{
  "match_score": 75,
  "missing_keywords": ["FastAPI", "Redis", "Docker"],
  "suggested_improvements": "1. Highlight experience with PostgreSQL query indexing. 2. Mention RESTful API design in your Apex Cloud summary.",
  "reasoning": "Strong core Python background, but could emphasize cloud-native microservices more clearly."
}}

JOB: {safe_title} at {safe_company}
DESCRIPTION:
{safe_desc}

AUTHENTIC RESUME:
{resume_text[:3500]}
'''
    try:
        response = ollama.chat(
            model='llama3.2',
            messages=[{'role': 'user', 'content': prompt}],
            format='json',
            options={'temperature': 0.1}
        )
        data = json.loads(response['message']['content'])
        return {
            "score": int(data.get("match_score", 0)),
            "missing_keywords": ", ".join(data.get("missing_keywords", [])),
            "improvements": str(data.get("suggested_improvements", "")),
            "reasoning": str(data.get("reasoning", ""))
        }
    except Exception as e:
        print(f"  [!] Ollama evaluation failed: {e}")
        return {
            "score": 50, "missing_keywords": "N/A",
            "improvements": "Ensure technical skills align with job description requirements.",
            "reasoning": "Fallback evaluation due to parsing error."
        }

# -------------------------------------------------------------
# 4. SCRAPING LAYER (ZipRecruiter Excluded)
# -------------------------------------------------------------
def fetch_all_jobs(existing_urls):
    all_jobs = []
    for role in SEARCH_ROLES:
        for loc in LOCATIONS:
            try:
                jobs_df = scrape_jobs(
                    site_name=["indeed", "linkedin"],
                    search_term=role,
                    location=loc,
                    results_wanted=RESULTS_PER_SEARCH,
                    hours_old=72,
                    is_remote=(loc.lower() == "remote")
                )
                if not jobs_df.empty:
                    all_jobs.append(jobs_df)
                    print(f"    [✓] Scraped {len(jobs_df)} listings for '{role}' - '{loc}'")
            except Exception as e:
                print(f"    [X] Platform block or timeout for '{role}' - '{loc}': {e}")
            time.sleep(2)

    if not all_jobs:
        return pd.DataFrame()

    combined = pd.concat(all_jobs, ignore_index=True).drop_duplicates(subset=["job_url"])
    unapplied = combined[~combined["job_url"].isin(existing_urls)]
    print(f"\n[*] Summary: Found {len(combined)} total leads ({len(combined) - len(unapplied)} logged previously, {len(unapplied)} fresh keys to process).")
    return unapplied

# -------------------------------------------------------------
# 5. RUNTIME ENGINE
# -------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  HEADLESS JOB INTELLIGENCE & SQL DATABASE CONNECTOR")
    print("=" * 60)

    resume_text = extract_text_from_pdf(BASE_RESUME_PDF_PATH)
    existing_urls = load_existing_urls()
    print(f"[*] Connected to local DB: {len(existing_urls)} tracked entries loaded.")

    listings = fetch_all_jobs(existing_urls)
    if listings.empty:
        print("[✓] Process complete. No new postings found today.")
        sys.exit(0)

    print(f"\n[*] Evaluating {len(listings)} entries using local AI metrics...\n")
    matched_count = 0

    for _, row in listings.iterrows():
        title = str(row.get("title", "") or "")
        company = str(row.get("company", "") or "")
        location = str(row.get("location", "") or "")
        desc = str(row.get("description", "") or "")
        url = str(row.get("job_url", "") or "")

        sen_reason = check_title_exclusions(title)
        if sen_reason:
            update_tracker(company, title, location, url, 0, "FILTERED", reasoning=sen_reason)
            continue

        avoid_reason = check_negative_keywords(title + " " + desc)
        if avoid_reason:
            update_tracker(company, title, location, url, 0, "FILTERED", reasoning=avoid_reason)
            continue

        desc_lower = desc.lower()
        title_lower = title.lower()
        hits = [kw for kw in TARGET_KEYWORDS if kw in desc_lower or kw in title_lower]
        if len(hits) < MINIMUM_KEYWORD_MATCHES:
            continue

        print(f"--> Auditing fit: {company} - {title}...")
        audit = audit_resume_and_suggest(title, company, desc, resume_text)

        status = "MATCHED" if audit["score"] >= MINIMUM_MATCH_SCORE else "LOW_SCORE"
        if status == "MATCHED":
            matched_count += 1
            print(f"    [★] MATCH ({audit['score']}%): Missing: {audit['missing_keywords']}")
        else:
            print(f"    [-] Score below benchmark ({audit['score']}%)")

        update_tracker(
            company=company, title=title, location=location, job_url=url,
            score=audit["score"], status=status, missing_kw=audit["missing_keywords"],
            improvements=audit["improvements"], reasoning=audit["reasoning"]
        )

    print("\n" + "=" * 60)
    print(f"[✓] Execution successful! {matched_count} matches written to secure local DB layers.")
    print("=" * 60)
