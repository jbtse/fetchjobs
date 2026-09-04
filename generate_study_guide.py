import os
import sys
import sqlite3
import collections
import ollama

DB_FILE = "application_tracker.db"
OUTPUT_GUIDE_FILE = "Interview_Study_Guide.md"

def fetch_missing_skills():
    if not os.path.exists(DB_FILE):
        print(f"[!] Error: Database '{DB_FILE}' not found. Run your job scanner script first.")
        sys.exit(1)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Extract roles and keywords specifically from strong system matches
    cursor.execute("SELECT role_title, company, missing_keywords FROM job_tracker WHERE status = 'MATCHED'")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("[!] No 'MATCHED' jobs found in the tracker database yet.")
        print("    Run the scanner script or lower your match score threshold to log targets.")
        sys.exit(0)
        
    all_keywords = []
    target_roles = set()
    
    for row in rows:
        role, company, keywords = row
        target_roles.add(f"{role} (at {company})")
        if keywords and keywords != "N/A":
            # Clean and split comma-separated keywords
            for kw in keywords.split(","):
                clean_kw = kw.strip()
                if clean_kw:
                    all_keywords.append(clean_kw)
                    
    # Find the most frequently requested skills to prioritize studying
    kw_counts = collections.Counter(all_keywords)
    return list(target_roles), kw_counts

def compile_study_guide_locally(roles, kw_counts):
    print(f"[*] Found {len(roles)} matched target roles.")
    print(f"[*] Analyzing {len(kw_counts)} unique missing technical keywords...")
    
    # Format the collected data for the local AI
    roles_list_str = "\n".join([f"- {r}" for r in roles])
    skills_priority_str = "\n".join([f"- {kw}: requested {count} times" for kw, count in kw_counts.most_common(12)])
    
    prompt = f"""You are an elite Technical Interview Coach and Senior Software Architect.
Your task is to compile a highly structured, comprehensive Technical Interview Study Guide for a candidate targeting these specific roles:

TARGET OPPORTUNITIES:
{roles_list_str}

PRIORITY MISSING TECHNOLOGIES IDENTIFIED (Focus heavily on these):
{skills_priority_str}

Provide a completely filled-out Markdown study plan containing:
1. EXECUTIVE GAP SUMMARY: Briefly analyze the primary architectural gaps based on the missing tech stacks.
2. 4-WEEK ROADMAP: Break down preparation into 4 sequential weeks. Each week must contain:
   - Specific core topics and deep concepts to learn.
   - Conceptual interview questions with expert answers (detailed answers, no placeholders).
   - High-yield practice projects/labs to build locally.
3. BEHAVIORAL BLUEPRINT: How to frame project experiences when missing these specific tools (using honest, valid phrasing).

Output direct, structured markdown. Do NOT use conversational preambles or chat greetings. Go straight into the Markdown content header.
"""
    
    try:
        print("[*] Generating comprehensive study guide via local Ollama engine...")
        response = ollama.chat(
            model='llama3.2',
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.3}
        )
        
        markdown_content = response['message']['content']
        
        with open(OUTPUT_GUIDE_FILE, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        print("\n" + "="*60)
        print(f"[✓] Success! Your customized Study Guide has been generated.")
        print(f"[✓] Saved to: {os.path.abspath(OUTPUT_GUIDE_FILE)}")
        print("="*60)
        
    except Exception as e:
        print(f"[!] Local LLM Study Guide compilation failed: {e}")

if __name__ == "__main__":
    target_roles, missing_skills = fetch_missing_skills()
    compile_study_guide_locally(target_roles, missing_skills)