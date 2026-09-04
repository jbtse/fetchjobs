import os
import sqlite3
import collections
import pandas as pd
import streamlit as st
import ollama

st.set_page_config(
    page_title="AI Job Search Copilot - Intelligence Hub",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Job Search Intelligence & Resume Optimizer")
st.markdown("Track opportunities, audit missing technical skills, and generate custom interview guides.")

DB_FILE = "application_tracker.db"
OUTPUT_GUIDE_FILE = "Interview_Study_Guide.md"

def load_data_from_db():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM job_tracker", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error reading SQL Database engine: {e}")
        return pd.DataFrame()

df = load_data_from_db()

if df.empty:
    st.info("No active records found in local `application_tracker.db` yet. Run your scraper pipeline script to begin.")
else:
    # KPI Metrics Bar
    total = len(df)
    matched = len(df[df["status"] == "MATCHED"])
    low_score = len(df[df["status"] == "LOW_SCORE"])
    filtered = len(df[df["status"] == "FILTERED"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Jobs Scanned", total)
    col2.metric("★ Strong System Matches", matched)
    col3.metric("Low Fit Scores", low_score)
    col4.metric("Excluded by Filtering", filtered)

    st.markdown("---")

    # Sidebar Controls
    st.sidebar.header("Filter & Search Controls")
    search_term = st.sidebar.text_input("Search Company or Role Title:", "")
    available_statuses = df["status"].unique().tolist()
    status_select = st.sidebar.multiselect(
        "Statuses to Display:",
        available_statuses,
        default=[s for s in ["MATCHED"] if s in available_statuses] or available_statuses
    )
    min_score = st.sidebar.slider("Minimum Match Score Benchmark:", 0, 100, 0)

    # Filter Logic
    view_df = df[df["status"].isin(status_select)]
    if "match_score" in view_df.columns:
        view_df = view_df[view_df["match_score"] >= min_score]
    if search_term:
        view_df = view_df[
            view_df["company"].str.contains(search_term, case=False, na=False) |
            view_df["role_title"].str.contains(search_term, case=False, na=False)
        ]

    # Tabs
    tab1, tab2, tab3 = st.tabs([
        "📋 Searchable Ledger & Open Links",
        "🔍 Resume Gap & Improvement Cards",
        "📚 Automated Technical Study Guide"
    ])

    with tab1:
        st.subheader("Application Ledger")
        st.markdown("Click **Open Job Posting** to apply via your desktop web browser.")
        display_cols = ["timestamp", "company", "role_title", "location", "match_score", "status", "job_url"]
        cols_to_use = [c for c in display_cols if c in view_df.columns]

        st.dataframe(
            view_df[cols_to_use].sort_values(by="match_score", ascending=False),
            use_container_width=True,
            column_config={
                "job_url": st.column_config.LinkColumn("Apply Link", display_text="Open Job Posting"),
                "match_score": st.column_config.ProgressColumn("Match Fit Score", min_value=0, max_value=100, format="%d%%")
            }
        )

    with tab2:
        st.subheader("Tailoring Recommendations")
        sorted_cards = view_df.sort_values(by="match_score", ascending=False)
        for _, row in sorted_cards.iterrows():
            with st.expander(f"{row['company']} — {row['role_title']} (Score: {row.get('match_score', 0)}%)"):
                st.markdown(f"**Application URL Link:** [{row['job_url']}]({row['job_url']})")
                st.markdown(f"**Location Details:** {row['location']} | **Status Classification:** `{row['status']}`")

                if row.get("missing_keywords"):
                    st.markdown("**Missing Structural Tech Keywords:**")
                    tags = [f"`{k.strip()}`" for k in str(row["missing_keywords"]).split(",") if k.strip()]
                    st.markdown(" ".join(tags))

                if row.get("suggested_improvements"):
                    st.markdown("**Suggested Resume Adjustments & Honest Phrase Gaps:**")
                    st.info(row["suggested_improvements"])

                if row.get("reasoning"):
                    st.markdown(f"**Recruiter Fit Assessment:** *{row['reasoning']}*")

    with tab3:
        st.subheader("Custom Technical Interview Coach")
        st.markdown("Generate targeted interview preparation plans customized to **specific opportunities** or your overall portfolio of matches.")

        eligible_jobs_df = df[df["status"].isin(["MATCHED", "APPLIED", "LOW_SCORE"])].copy()

        if eligible_jobs_df.empty:
            st.warning("⚠️ No eligible opportunities found in your database yet. Run your pipeline runner to seed records.")
        else:
            mode = st.radio(
                "Study Guide Target Scope:",
                ["🎯 Specific Opportunity (Deep-Dive)", "📊 Selected / Multiple Opportunities", "🌐 All Matched Jobs (Aggregated)"],
                horizontal=True
            )

            selected_jobs = []

            if mode == "🎯 Specific Opportunity (Deep-Dive)":
                job_options = {
                    f"{row['company']} — {row['role_title']} (Match: {row.get('match_score', 0)}%)": row
                    for _, row in eligible_jobs_df.sort_values(by="match_score", ascending=False).iterrows()
                }
                chosen_label = st.selectbox("Select Target Position:", list(job_options.keys()))
                if chosen_label:
                    selected_jobs = [job_options[chosen_label]]

            elif mode == "📊 Selected / Multiple Opportunities":
                job_options = {
                    f"{row['company']} — {row['role_title']} (Match: {row.get('match_score', 0)}%)": row
                    for _, row in eligible_jobs_df.sort_values(by="match_score", ascending=False).iterrows()
                }
                chosen_labels = st.multiselect(
                    "Select Target Opportunities to Combine:",
                    options=list(job_options.keys()),
                    default=list(job_options.keys())[:min(3, len(job_options))]
                )
                selected_jobs = [job_options[lbl] for lbl in chosen_labels]

            else:
                matched_only = eligible_jobs_df[eligible_jobs_df["status"] == "MATCHED"]
                selected_jobs = [row for _, row in (matched_only if not matched_only.empty else eligible_jobs_df).iterrows()]

            if not selected_jobs:
                st.info("Select at least one job above to compile a study guide.")
            else:
                st.markdown(f"**Targeting {len(selected_jobs)} Opportunity / Opportunities:**")
                for job in selected_jobs:
                    st.caption(f"• **{job['company']}** — {job['role_title']} (Missing: `{job.get('missing_keywords', 'None')}`)")

                study_timeline = st.select_slider(
                    "Preparation Timeline Depth:",
                    options=["⚡ Intensive 1-Week Crash Course", "🎯 Focused 2-Week Plan", "📚 Comprehensive 4-Week Mastery"],
                    value="🎯 Focused 2-Week Plan"
                )

                if st.button("🚀 Compile Tailored Study Guide (Via Ollama)", use_container_width=True):
                    with st.spinner("Analyzing specific role requirements and compiling deep-dive guide via local Ollama..."):
                        target_context_blocks = []
                        all_missing_keywords = []

                        for job in selected_jobs:
                            block = f'''COMPANY: {job['company']}
ROLE: {job['role_title']}
LOCATION: {job['location']}
MATCH SCORE: {job.get('match_score', 0)}%
MISSING/GAP KEYWORDS: {job.get('missing_keywords', 'None')}
RECRUITER REASONING: {job.get('reasoning', '')}
SUGGESTED RESUME IMPROVEMENTS: {job.get('suggested_improvements', '')}
'''
                            target_context_blocks.append(block)
                            if job.get("missing_keywords") and job["missing_keywords"] != "N/A":
                                for kw in str(job["missing_keywords"]).split(","):
                                    clean_kw = kw.strip()
                                    if clean_kw:
                                        all_missing_keywords.append(clean_kw)

                        kw_summary = collections.Counter(all_missing_keywords)
                        aggregated_context = "\n---\n".join(target_context_blocks)
                        priority_skills = ", ".join([f"{k} (x{v})" for k, v in kw_summary.most_common(10)]) if kw_summary else "General Core Competencies"

                        prompt = f'''You are an elite Technical Interview Coach and Principal Software Architect.
Create a high-impact, custom Technical Interview Study Guide tailored strictly to the candidate's selected opportunity/opportunities.

TARGET ROLE CONTEXT & GAP ANALYSIS:
{aggregated_context}

KEY DEFICITS / PRIORITY TECHNICAL TOOLS IDENTIFIED:
{priority_skills}

TIMELINE REQUESTED: {study_timeline}

Generate a comprehensive, actionable Markdown preparation manual containing:
1. TARGET COMPANY & ROLE PROFILE: Deep-dive into what this specific team cares about, expected system scales, and interview rounds.
2. TAILORED ARCHITECTURAL & TECHNICAL ROADMAP: Break down preparation into structured phases ({study_timeline}).
   - For every week/phase, cover:
     * Theoretical mastery topics targeting the exact missing keywords.
     * 3-4 High-probability real-world technical interview questions with deep, complete answer explanations.
     * Concrete hands-on coding lab or architecture design exercise simulating the company's domain.
3. SYSTEM DESIGN SCENARIO: A full system design problem typical of this specific company/role with an optimal architectural breakdown.
4. HONEST DEFENSE BLUEPRINT: Explicit scripts and talking points for addressing the missing tools during interviews without lying.

Provide direct, structured markdown. Do NOT use conversational preambles or chat greetings.
'''
                        try:
                            response = ollama.chat(
                                model='llama3.2',
                                messages=[{'role': 'user', 'content': prompt}],
                                options={'temperature': 0.3}
                            )
                            guide_content = response['message']['content']

                            with open(OUTPUT_GUIDE_FILE, "w", encoding="utf-8") as f:
                                f.write(guide_content)

                            st.success(f"✨ Custom Study Guide compiled and saved to `{OUTPUT_GUIDE_FILE}`!")
                            st.markdown("### 📚 Your Targeted Preparation Guide")
                            st.markdown(guide_content)
                        except Exception as e:
                            st.error(f"Failed to generate study guide via Ollama: {e}")

                elif os.path.exists(OUTPUT_GUIDE_FILE):
                    st.markdown("---")
                    st.markdown("### 📖 Previously Generated Guide")
                    with open(OUTPUT_GUIDE_FILE, "r", encoding="utf-8") as f:
                        st.markdown(f.read())
