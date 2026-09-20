from fastapi import APIRouter

router = APIRouter()

# Placeholder for HTMX API routes
@router.post("/upload")
def upload_resume():
    return {"message": "Upload resume"}
