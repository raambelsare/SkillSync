import warnings
warnings.filterwarnings("ignore")
from pypdf import PdfReader
import io
import re
from lib.scoring import SKILLS_LIST

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts all text from a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def extract_skills(text: str) -> list:
    """
    Extracts skills by matching against the known skills list.
    Uses regex word boundaries for accurate matching.
    """
    extracted = []
    text_lower = (text or "").lower()
    for skill in SKILLS_LIST:
        # Regex to match whole words/phrases, escaping special characters like C++
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, text_lower):
            extracted.append(skill)
    return extracted

def extract_years_of_experience(text: str) -> int:
    """
    Attempts to extract total years of experience using regex patterns.
    Looks for phrases like '5 years of experience', '3+ years', etc.
    Returns 0 if none found.
    """
    text_lower = (text or "").lower()
    
    # Matches "X years" or "X+ years" where X is a digit or word
    patterns = [
        r'(\d+)\s*\+?\s*years?(?:\s*of)?\s*experience',
        r'experience(?:.*?)(\d+)\s*\+?\s*years?',
    ]
    
    max_years = 0
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            try:
                years = int(match)
                if 0 < years < 40 and years > max_years: # Sanity check upper bound
                    max_years = years
            except (ValueError, TypeError):
                pass
                
    return max_years

