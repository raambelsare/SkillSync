from fastapi import APIRouter

router = APIRouter()

# Placeholder for HTML page routes
@router.get("/")
def home():
    return {"message": "Home page"}
