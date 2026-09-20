import os
import warnings
warnings.filterwarnings("ignore")
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from lib.database import supabase

def get_current_user(request: Request):
    """Dependency to extract user from Supabase cookie and validate session."""
    token = request.cookies.get("sb-access-token")
    if not token:
        return None
    
    try:
        user_resp = supabase.auth.get_user(token)
        if not user_resp or not user_resp.user:
            return None
        user = user_resp.user

        # Get role by checking students and admins tables
        student_data = supabase.table("students").select("id, name").eq("id", user.id).execute()
        if student_data.data:
            return {"user": user, "role": "student", "name": student_data.data[0]["name"]}
        
        admin_data = supabase.table("admins").select("id, name").eq("id", user.id).execute()
        if admin_data.data:
            return {"user": user, "role": "admin", "name": admin_data.data[0]["name"]}

        return None
    except Exception:
        return None

def get_current_student(user: Optional[dict] = Depends(get_current_user)):
    """Return the user if authenticated as student, else raise 307 redirect to /login."""
    if not user or user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return user

def get_current_admin(user: Optional[dict] = Depends(get_current_user)):
    """Return the user if authenticated as admin, else raise 307 redirect to /login."""
    if not user or user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return user
