# fetchjobs
All encompassing tool for your job search (hopefully)

Possible future features:
1. use google advanced search to also find jobs with googlesearch-python package
2. get around bot scraping barriers on ziprecruiter and other sites

Setup Instructions:

1.  Install dependencies: pip install -r requirements.txt

Run Instructions:
1.  Fill out Configuration fields in job_pipeline_with_tracker.py
2.  Place your resume in the same directory as job_pipeline_with_tracker.py
3.  Run Ollama: ollama run llama3.2
4.  Keep Ollama running in the background with ctrl + D
5.  Run the scanner script: python job_pipeline_with_tracker.py
    - It scans listings, audits them against my_resume.pdf, and logs all recommendations, missing keywords, and posting links to application_tracker.csv.
6.  (Optional) Generate an overall study guide: python generate_study_guide.py
7.  Open your interactive dashboard: streamlit run dashboard.py
    - Browse high-match opportunities, read your customized bullet improvements, and click "Open Job Posting" to apply directly in your personal, everyday web browser with all your personal accounts already signed in.
    - Generate a custom study guide for all your opportunities
