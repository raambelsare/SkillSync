import os
import re
import json

def load_skills():
    try:
        skills_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills.json")
        with open(skills_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

SKILLS_LIST = load_skills()

def calculate_ats_score(resume_text: str, extracted_skills: list, required_skills: list, years_extracted: int, years_required: int = 1):
    """
    Calculates the ATS score deterministically.
    """
    # 1. Keyword Match Score (Weight: 60%)
    if not required_skills:
        keyword_match_score = 100.0
    else:
        matched_required = [s for s in required_skills if s.lower() in [es.lower() for es in extracted_skills]]
        keyword_match_score = (len(matched_required) / len(required_skills)) * 100

    # 2. Formatting Score (Weight: 25%)
    # Checks worth 25 points each (max 100)
    formatting_score = 0
    text_lower = (resume_text or "").lower()
    
    # Check 1: Contact Info (Email or Phone)
    has_email = re.search(r'[\w.-]+@[\w.-]+', text_lower)
    has_phone = re.search(r'\+?\d{10,14}', text_lower.replace('-', '').replace(' ', ''))
    if has_email or has_phone:
        formatting_score += 25
        
    # Check 2: Education heading
    if re.search(r'\b(education|academic background)\b', text_lower):
        formatting_score += 25
        
    # Check 3: Experience heading
    if re.search(r'\b(experience|work history|employment)\b', text_lower):
        formatting_score += 25
        
    # Check 4: Skills heading
    if re.search(r'\b(skills|technical skills|competencies)\b', text_lower):
        formatting_score += 25

    # 3. Experience Score (Weight: 15%)
    years_extracted = years_extracted or 0
    if years_required <= 0:
        experience_score = 100.0
    else:
        experience_score = min(years_extracted / years_required, 1.0) * 100

    # Final Score Calculation
    final_score = (0.6 * keyword_match_score) + (0.25 * formatting_score) + (0.15 * experience_score)
    
    return {
        "score": round(final_score),
        "keyword_match": round(keyword_match_score),
        "formatting_score": formatting_score
    }


