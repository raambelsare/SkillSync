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

# Industry-standard action verbs that demonstrate active professional experience and ownership
ACTION_VERBS = [
    "developed", "designed", "implemented", "built", "created", "engineered",
    "managed", "led", "spearheaded", "optimized", "architected", "deployed",
    "collaborated", "automated", "maintained", "analyzed", "configured",
    "integrated", "refactored", "resolved", "launched", "coordinated",
    "established", "executed", "programmed", "supervised", "streamlined"
]

def evaluate_experience_score(resume_text: str, years_extracted: int, years_required: int = 1) -> float:
    """
    Analyzes candidate experience from resume text and extracted years:
    1. Tenure / Duration Matching (Max 40 points)
    2. Strong Action & Execution Verbs (Max 30 points)
    3. Quantifiable Achievements & Measurable Impact (Max 30 points)
    Returns an experience score out of 100.
    """
    text_lower = (resume_text or "").lower()
    years_extracted = years_extracted or 0

    # 1. Tenure & Role Exposure (Max 40 points)
    if years_required <= 0:
        tenure_score = 40.0
    elif years_extracted >= years_required:
        tenure_score = 40.0
    elif years_extracted > 0:
        tenure_score = (years_extracted / years_required) * 40.0
    else:
        # Check for internship, co-op, freelance, or active project roles if formal years not stated
        practical_patterns = [
            r"\bintern(?:ship)?\b",
            r"\bfreelanc(?:e|er)\b",
            r"\bco-?op\b",
            r"\bproject\b",
            r"\bcontributor\b",
            r"\bopen source\b"
        ]
        has_practical = any(re.search(p, text_lower) for p in practical_patterns)
        tenure_score = 25.0 if has_practical else 10.0

    # 2. Action Verbs & Responsibility (Max 30 points)
    matched_verbs = [v for v in ACTION_VERBS if re.search(r"\b" + v + r"\b", text_lower)]
    verb_count = len(matched_verbs)
    if verb_count >= 6:
        verbs_score = 30.0
    elif verb_count >= 4:
        verbs_score = 22.0
    elif verb_count >= 2:
        verbs_score = 15.0
    elif verb_count >= 1:
        verbs_score = 8.0
    else:
        verbs_score = 0.0

    # 3. Measurable Impact & Quantifiable Results (Max 30 points)
    metric_patterns = [
        r"\b\d+\s*%",
        r"\b\d+\s*x\b",
        r"\$\s*\d+",
        r"\b\d+k\+?\b",
        r"\b(?:increased|reduced|improved|decreased|accelerated|boosted|saved)\s+(?:by\s+)?\d+",
        r"\b(?:scaled|serving|processed|managed)\s+(?:to\s+)?\d+"
    ]
    matched_metrics = 0
    for pattern in metric_patterns:
        matched_metrics += len(re.findall(pattern, text_lower))

    if matched_metrics >= 3:
        metrics_score = 30.0
    elif matched_metrics == 2:
        metrics_score = 20.0
    elif matched_metrics == 1:
        metrics_score = 12.0
    else:
        metrics_score = 0.0

    return min(tenure_score + verbs_score + metrics_score, 100.0)

def calculate_ats_score(resume_text: str, extracted_skills: list, required_skills: list, years_extracted: int, years_required: int = 1):
    """
    Calculates the ATS score deterministically:
    - Keyword Match Score (Weight: 50%)
    - Formatting Score (Weight: 20%)
    - Experience & Impact Score (Weight: 30%)
    """
    # 1. Keyword Match Score (Weight: 50%)
    if not required_skills:
        keyword_match_score = 100.0
    else:
        matched_required = [s for s in required_skills if s.lower() in [es.lower() for es in extracted_skills]]
        keyword_match_score = (len(matched_required) / len(required_skills)) * 100

    # 2. Formatting Score (Weight: 20%)
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

    # 3. Experience & Measurable Impact Score (Weight: 30%)
    experience_score = evaluate_experience_score(resume_text, years_extracted, years_required)

    # Final ATS Score Calculation
    final_score = (0.50 * keyword_match_score) + (0.20 * formatting_score) + (0.30 * experience_score)
    
    return {
        "score": round(final_score),
        "keyword_match": round(keyword_match_score),
        "formatting_score": formatting_score,
        "experience_score": round(experience_score)
    }



