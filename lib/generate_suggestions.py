import os
import warnings
warnings.filterwarnings("ignore")
from typing import List
# pyrefly: ignore [missing-import]
from google import genai


def generate_improvement_suggestions(missing_skills: List[str], target_job_title: str) -> str:
    """
    Calls the Google Gemini API for resume improvement suggestions.
    Falls back to a generic string if the API fails.
    """
    fallback_text = f"Consider learning or emphasizing these missing skills: {', '.join(missing_skills)}."
    
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        return fallback_text
        
    if not missing_skills:
        return "Your resume covers all the required skills well. Focus on highlighting specific achievements in these areas."
        
    prompt = f"""
    You are an expert career coach helping a candidate improve their resume.
    I am applying for a "{target_job_title}" role. 
    My resume is missing the following key skills: {', '.join(missing_skills)}.
    Provide 3 concise, actionable suggestions (bullet points) on how I can improve my resume or what I should learn to be a better fit for this role.
    Keep the response short and direct.
    """
    
    try:
        client = genai.Client(api_key=google_api_key)
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            parts: List[str] = []
            for p in response.candidates[0].content.parts:
                p_text = getattr(p, "text", None)
                if p_text:
                    parts.append(str(p_text))
            result = "".join(parts).strip()
            if result:
                return result
        return fallback_text
    except Exception:
        return fallback_text


