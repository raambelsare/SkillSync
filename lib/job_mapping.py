import urllib.parse

JOB_ROLES = {
    "Frontend Developer": ["JavaScript", "TypeScript", "HTML", "CSS", "React", "Next.js", "Vue", "Angular", "Tailwind CSS", "Figma", "UI/UX"],
    "Backend Developer": ["Python", "Node.js", "Express", "FastAPI", "Django", "Java", "Spring Boot", "Go", "Ruby", "SQL", "PostgreSQL", "MongoDB", "Redis"],
    "Full Stack Developer": ["JavaScript", "TypeScript", "Python", "React", "Node.js", "Express", "SQL", "PostgreSQL", "MongoDB", "AWS", "Docker"],
    "Data Scientist": ["Python", "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Scikit-Learn", "Pandas", "NumPy", "SQL", "Data Analysis"],
    "Data Engineer": ["Python", "SQL", "AWS", "GCP", "PostgreSQL", "Spark", "Hadoop", "ETL", "Data Warehousing", "Airflow"],
    "DevOps Engineer": ["AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "CI/CD", "GitHub Actions", "Git", "Linux", "Python", "Go"],
    "Mobile Developer": ["Swift", "Kotlin", "React Native", "Flutter", "Java", "Mobile UI", "iOS", "Android"],
    "Cloud Architect": ["AWS", "GCP", "Azure", "Terraform", "Kubernetes", "Docker", "System Design", "Networking", "Security"],
    "Machine Learning Engineer": ["Python", "C++", "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "AWS", "GCP", "Docker", "Model Deployment"],
    "Product Manager": ["Agile", "Scrum", "Jira", "Confluence", "Communication", "Leadership", "Product Strategy", "Data Analysis", "UI/UX"]
}

def get_recommended_roles(extracted_skills, top_n=5):
    if not extracted_skills:
        return []

    extracted_lower = [s.lower() for s in extracted_skills]
    
    scored_roles = []
    for title, req_skills in JOB_ROLES.items():
        matched = [s for s in req_skills if s.lower() in extracted_lower]
        overlap_count = len(matched)
        if len(req_skills) > 0:
            match_percent = int((overlap_count / len(req_skills)) * 100)
        else:
            match_percent = 0
            
        query = urllib.parse.quote(title)
        # Include roles even with 0% so user sees something - but still sort by match
        scored_roles.append({
            "title": title,
            "match_percent": match_percent,
            "overlap": ", ".join(matched) if matched else "No direct matches",
            "links": {
                "LinkedIn": f"https://www.linkedin.com/jobs/search/?keywords={query}",
                "Indeed": f"https://www.indeed.com/jobs?q={query}",
                "Glassdoor": f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}"
            }
        })
            
    # Sort by match percent descending
    ranked = sorted(scored_roles, key=lambda x: x["match_percent"], reverse=True)
    return ranked[:top_n]
