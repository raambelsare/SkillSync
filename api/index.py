import warnings
warnings.filterwarnings("ignore")

import os
import time
from typing import Optional
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env using absolute path so credentials are always available
# regardless of working directory or import order
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=_env_path, override=True)

from lib.database import supabase, get_supabase
from lib.auth import get_current_user, get_current_student, get_current_admin
from lib.parser import extract_text_from_pdf, extract_skills, extract_years_of_experience
from lib.scoring import calculate_ats_score
from lib.generate_suggestions import generate_improvement_suggestions
from lib.job_mapping import get_recommended_roles
from urllib.parse import quote_plus

app = FastAPI(title="SkillSync")

# Enable CORS for seamless cross-domain deployments (e.g. Render backend + Vercel frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def get_site_url(request: Request = None) -> str:
    """Resolve the canonical site URL.

    Priority:
    1. SITE_URL          – explicit override (any environment)
    2. VERCEL_PROJECT_PRODUCTION_URL – Vercel stable production domain (auto-set by Vercel)
    3. VERCEL_URL        – per-deployment unique URL (auto-set by Vercel)
    4. request.base_url  – local fallback
    """
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"].rstrip("/")
    if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"):
        return f"https://{os.environ['VERCEL_PROJECT_PRODUCTION_URL']}"
    if os.environ.get("VERCEL_URL"):
        return f"https://{os.environ['VERCEL_URL']}"
    if request:
        return str(request.base_url).rstrip("/")
    return ""

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# Super-admin credentials — read AFTER dotenv is loaded above
SUPER_ADMIN_EMAIL    = os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@skillsync.com")
SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "superadmin123")

print(f"[boot] Super-admin email loaded: {SUPER_ADMIN_EMAIL}")

# ---------------------------------------------------------------------------
# Helper: ensure user exists in public.users before inserting into sub-tables
# ---------------------------------------------------------------------------
def _ensure_public_user(user_id: str, email: str, name: str) -> bool:
    """
    Upserts a row into public.users so downstream FK constraints are satisfied.
    After the FK-fix SQL patch, students/admins reference auth.users directly,
    so a failure here is non-fatal — we log it and return False.
    Returns True if the upsert succeeded.
    """
    for payload in [
        {"id": user_id, "email": email, "name": name},
        {"id": user_id, "email": email},
        {"id": user_id},
    ]:
        try:
            supabase.table("users").upsert(payload, on_conflict="id").execute()
            print(f"[_ensure_public_user] upserted public.users for {user_id}")
            return True
        except Exception as e:
            print(f"[_ensure_public_user] attempt with payload {list(payload.keys())} failed: {e}")
    print(f"[_ensure_public_user] WARNING: all attempts failed for {user_id} — continuing anyway")
    return False


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_root(request: Request, user: dict = Depends(get_current_user)):
    if request.method == "HEAD":
        return HTMLResponse(content="")
    if user:
        if user.get("role") == "admin":
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("index.html", {"request": request})

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok"}



@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, tab: str = "user"):
    return templates.TemplateResponse("login.html", {"request": request, "tab": tab})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def student_dashboard(request: Request, user: dict = Depends(get_current_student)):
    return templates.TemplateResponse("student_dashboard.html", {"request": request, "user": user})

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: dict = Depends(get_current_admin)):
    # Jobs posted by this recruiter
    try:
        jobs = supabase.table("jobs").select("*").execute().data
    except Exception:
        jobs = []

    # Applications for recruiter's jobs — join student ATS scores for top-resume view
    try:
        applications_query = supabase.table("applications").select(
            "id, status, applied_at, students(name), jobs(title)"
        ).execute()
        applications = applications_query.data
    except Exception:
        applications = []


    # Top resumes: fetch resume_analysis + ats_scores, pick top 5 by score
    try:
        scores_data = supabase.table("ats_scores").select(
            "score, resume_id, resumes(student_id, students(name))"
        ).order("score", desc=True).limit(10).execute().data
        top_resumes = []
        for row in scores_data:
            resume = row.get("resumes") or {}
            student = resume.get("students") or {}
            top_resumes.append({
                "name":  student.get("name", "Unknown"),
                "score": row.get("score", 0),
            })
    except Exception:
        top_resumes = []

    return templates.TemplateResponse("admin_dashboard.html", {
        "request":      request,
        "user":         user,
        "jobs":         jobs,
        "applications": applications,
        "top_resumes":  top_resumes,
    })

@app.get("/superadmin", response_class=HTMLResponse)
async def superadmin_dashboard(request: Request):
    # Simple cookie-based gate
    if request.cookies.get("sa-session") != "1":
        return RedirectResponse(url="/login?tab=superadmin", status_code=302)

    # --- Stats ---
    try:
        total_resumes = len(supabase.table("resumes").select("id").execute().data)
    except Exception:
        total_resumes = 0

    try:
        all_scores = supabase.table("ats_scores").select(
            "score, resume_id, resumes(student_id, students(name))"
        ).order("score", desc=True).execute().data
    except Exception:
        all_scores = []

    best_resume = None
    if all_scores:
        top = all_scores[0]
        resume = top.get("resumes") or {}
        student = resume.get("students") or {}
        best_resume = {
            "name":  student.get("name", "Unknown"),
            "score": top.get("score", 0),
        }

    # Most likely to get recruited = highest ATS score AND has applied to jobs
    most_likely = None
    try:
        apps = supabase.table("applications").select(
            "student_id, students(name)"
        ).execute().data
        applied_ids = {a["student_id"] for a in apps if a.get("student_id")}
        for row in all_scores:
            resume = row.get("resumes") or {}
            sid = resume.get("student_id")
            if sid in applied_ids:
                student = resume.get("students") or {}
                most_likely = {
                    "name":  student.get("name", "Unknown"),
                    "score": row.get("score", 0),
                }
                break
    except Exception:
        pass

    # All resumes ranked
    ranked = []
    for row in all_scores:
        resume = row.get("resumes") or {}
        student = resume.get("students") or {}
        ranked.append({
            "name":  student.get("name", "Unknown"),
            "score": row.get("score", 0),
        })

    return templates.TemplateResponse("superadmin_dashboard.html", {
        "request":       request,
        "total_resumes": total_resumes,
        "best_resume":   best_resume,
        "most_likely":   most_likely,
        "ranked":        ranked,
    })


# ---------------------------------------------------------------------------
# Auth Actions
# ---------------------------------------------------------------------------

@app.get("/auth/google")
async def auth_google(request: Request, role: Optional[str] = None):

    try:
        # Build the OAuth URL manually to guarantee implicit flow (response_type=token).
        # The gotrue-py client may override query_params and force PKCE, which breaks
        # server-side Python (no code_verifier available). Constructing the URL directly
        # ensures Supabase always returns #access_token= in the hash (implicit flow).
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        redirect_to  = f"{get_site_url(request)}/auth/callback"
        import urllib.parse
        params = urllib.parse.urlencode({
            "provider":      "google",
            "redirect_to":   redirect_to,
            "response_type": "token",   # implicit flow — tokens in URL hash
        })
        oauth_url = f"{supabase_url}/auth/v1/authorize?{params}"

        response = RedirectResponse(url=oauth_url)
        if role in ("student", "admin"):
            response.set_cookie(key="oauth_role", value=role, max_age=600, httponly=True)
        return response
    except Exception as e:
        print(f"[auth/google] error: {e}")
        return RedirectResponse(url="/login?error=Google auth failed")

@app.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    # Implicit flow: Supabase sends #access_token= in the URL hash.
    # The hash is never sent to the server, so we serve the HTML page and
    # let auth_callback.html extract the token client-side, then POST to /auth/set-session.
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@app.post("/auth/set-session")
async def set_session(request: Request, access_token: str = Form(...), refresh_token: str = Form("")):
    try:
        user_res = supabase.auth.get_user(access_token)
        if user_res and getattr(user_res, "user", None):
            user = user_res.user
            user_id   = user.id
            user_metadata = getattr(user, "user_metadata", {}) or {}
            user_name = user_metadata.get("full_name", "Google User") if isinstance(user_metadata, dict) else "Google User"
            user_email = getattr(user, "email", "") or ""


            student_exists = supabase.table("students").select("id").eq("id", user_id).execute().data
            admin_exists   = supabase.table("admins").select("id").eq("id", user_id).execute().data

            is_new_recruiter = False
            oauth_role = request.cookies.get("oauth_role", "student")

            if not student_exists and not admin_exists:
                _ensure_public_user(user_id, user_email, user_name)
                if oauth_role == "admin":
                    supabase.table("admins").insert({"id": user_id, "name": user_name}).execute()
                    is_new_recruiter = True
                else:
                    supabase.table("students").insert({"id": user_id, "name": user_name}).execute()

            if is_new_recruiter or admin_exists:
                redirect_url = "/recruiter/onboarding" if is_new_recruiter else "/admin"
            else:
                redirect_url = "/dashboard"

            response = RedirectResponse(url=redirect_url, status_code=302)
            response.set_cookie(key="sb-access-token", value=access_token, httponly=True)
            response.delete_cookie("oauth_role")
            return response
            
        return RedirectResponse(url="/login?error=Invalid session", status_code=302)
    except Exception as e:
        print(f"Error setting session: {e}")
        return RedirectResponse(url="/login?error=Failed to complete Google sign-in", status_code=302)

@app.post("/auth/signup")
async def signup_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
):
    try:
        # Validate role
        if role not in ("student", "admin"):
            return templates.TemplateResponse("signup.html", {
                "request": request, "error": "Invalid account type."
            })

        # 1. Create the auth user
        # Using admin.create_user with email_confirm=True avoids SMTP delivery timeouts and confirmation locks
        user_id = None
        admin_client = get_supabase()
        try:
            res = admin_client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name, "role": role},
            })
            if res and res.user:
                user_id = res.user.id
                print(f"[signup] admin created user: {user_id}")
        except Exception as admin_err:
            err_lower = str(admin_err).lower()
            if "already registered" in err_lower or "already exists" in err_lower or "duplicate" in err_lower:
                return templates.TemplateResponse("signup.html", {
                    "request": request,
                    "error": "An account with this email already exists. Please log in.",
                })
            print(f"[signup] admin.create_user failed ({admin_err}), trying standard sign_up...")
            res = supabase.auth.sign_up({"email": email, "password": password})
            if not res or not res.user:
                return templates.TemplateResponse("signup.html", {
                    "request": request,
                    "error": "Signup failed. The email may already be registered.",
                })
            user_id = res.user.id
            print(f"[signup] standard auth.users created: {user_id}")

        if not user_id:
            return templates.TemplateResponse("signup.html", {
                "request": request,
                "error": "Could not create user account. Please check your details and try again.",
            })

        # 2. Upsert public.users as a safety net (also called in retry loop)
        _ensure_public_user(user_id, email, name)

        # 3. Insert into students or admins with retry on FK violations
        table_name = "students" if role == "student" else "admins"
        last_error = None

        for attempt in range(5):
            try:
                supabase.table(table_name).upsert(
                    {"id": user_id, "name": name},
                    on_conflict="id",
                ).execute()
                last_error = None
                print(f"[signup] inserted into {table_name} on attempt {attempt + 1}")
                break
            except Exception as insert_err:
                last_error = insert_err
                err_str = str(insert_err)
                print(f"[signup] attempt {attempt + 1} failed on {table_name}: {err_str}")

                # Only retry FK violations (23503)
                if "23503" not in err_str and "foreign key" not in err_str.lower():
                    raise

                # Diagnose: check what public.users holds right now
                try:
                    check = supabase.table("users").select("id,email").eq("id", user_id).execute()
                    print(f"[signup] public.users row at attempt {attempt + 1}: {check.data}")
                except Exception as ce:
                    print(f"[signup] could not check public.users: {ce}")

                # Re-upsert and wait
                _ensure_public_user(user_id, email, name)
                time.sleep(1.5)

        if last_error:
            # Clean up the orphaned auth user so they can retry
            try:
                admin_cleanup = get_supabase()
                admin_cleanup.auth.admin.delete_user(user_id)
                print(f"[signup] cleaned up auth user {user_id} after failure")
            except Exception as de:
                print(f"[signup] could not delete auth user: {de}")

            return templates.TemplateResponse("signup.html", {
                "request": request,
                "error": (
                    "Account setup failed due to a database configuration error. "
                    f"Detail: {last_error}"
                ),
            })

        # 4. Auto-login
        try:
            auth_client = get_supabase()
            login_res = auth_client.auth.sign_in_with_password({"email": email, "password": password})
            if login_res and login_res.session:
                redirect_url = "/dashboard" if role == "student" else "/recruiter/onboarding"
                response = RedirectResponse(url=redirect_url, status_code=302)
                response.set_cookie(
                    key="sb-access-token",
                    value=login_res.session.access_token,
                    httponly=True,
                    samesite="lax",
                )
                return response
        except Exception as login_err:
            print(f"[signup] auto-login after signup failed: {login_err}")

        # If auto-login didn't complete session, redirect to login page
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Account created successfully! Please log in.",
            "tab": "user",
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        err_msg = str(e)
        if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
            friendly_err = "The authentication service request timed out. Please check your internet connection and try again."
        elif "already registered" in err_msg.lower() or "already exists" in err_msg.lower():
            friendly_err = "An account with this email already exists. Please log in."
        else:
            friendly_err = f"Account creation failed: {err_msg}"
        return templates.TemplateResponse("signup.html", {"request": request, "error": friendly_err})

# ---------------------------------------------------------------------------
# Recruiter Onboarding Routes
# ---------------------------------------------------------------------------
@app.get("/recruiter/onboarding", response_class=HTMLResponse)
async def get_recruiter_onboarding(request: Request, user: dict = Depends(get_current_admin)):
    return templates.TemplateResponse("recruiter_onboarding.html", {"request": request, "user": user})

@app.post("/api/recruiter/onboard")
async def post_recruiter_onboard(
    request: Request,
    company_name: str = Form(...),
    job_title: Optional[str] = Form(None),
    job_description: Optional[str] = Form(None),
    job_location: Optional[str] = Form(None),
    job_salary: Optional[str] = Form(None),
    user: dict = Depends(get_current_admin)
):

    try:
        user_id = user['user'].id

        # 1. Check if company exists or create a new one
        company_res = supabase.table("companies").select("id").eq("name", company_name).execute()
        if company_res.data:
            company_id = company_res.data[0]["id"]
        else:
            new_comp = supabase.table("companies").insert({"name": company_name}).execute()
            company_id = new_comp.data[0]["id"]

        # 2. Optionally create a job posting
        if job_title:
            salary_val = float(job_salary) if job_salary and job_salary.strip() else None
            supabase.table("jobs").insert({
                "company_id": company_id,
                "title": job_title,
                "description": job_description or "",
                "location": job_location or "Remote",
                "salary": salary_val,
                "posted_by": user_id
            }).execute()

        # Redirect to the main admin dashboard after successful onboarding
        return RedirectResponse(url="/admin", status_code=302)
    except Exception as e:
        import traceback; traceback.print_exc()
        return templates.TemplateResponse("recruiter_onboarding.html", {
            "request": request,
            "user": user,
            "error": f"Failed to complete onboarding: {str(e)}"
        })

@app.post("/auth/login")
async def login_action(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if not res or not res.user or not res.session:
            return templates.TemplateResponse("login.html", {
                "request": request, "error": "Invalid credentials.", "tab": "user"
            })
        student_data = supabase.table("students").select("id").eq("id", res.user.id).execute()
        redirect_url = "/dashboard" if student_data.data else "/admin"
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(key="sb-access-token", value=res.session.access_token, httponly=True)
        return response

    except Exception:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid credentials.", "tab": "user"
        })

@app.post("/auth/superadmin-login")
async def superadmin_login(request: Request, email: str = Form(...), password: str = Form(...)):
    print(f"[sa-login] attempt: email={email!r}  expected={SUPER_ADMIN_EMAIL!r}  pw_match={password == SUPER_ADMIN_PASSWORD}")
    if email == SUPER_ADMIN_EMAIL and password == SUPER_ADMIN_PASSWORD:
        response = RedirectResponse(url="/superadmin", status_code=302)
        response.set_cookie(key="sa-session", value="1", httponly=True)
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "sa_error": f"Invalid super-admin credentials. (expected email: {SUPER_ADMIN_EMAIL})",
        "tab": "superadmin"
    })

@app.post("/auth/logout")
async def logout_action():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sa-session")
    return response


# ---------------------------------------------------------------------------
# HTMX Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/upload-resume", response_class=HTMLResponse)
async def upload_resume(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_student)):
    try:
        file_bytes = await file.read()

        file_path = f"{user['user'].id}/{file.filename}"
        supabase.storage.from_("resumes").upload(file_path, file_bytes, {"upsert": "true"})

        resume_record = supabase.table("resumes").insert({
            "student_id": user['user'].id,
            "storage_path": file_path
        }).execute()
        resume_id = resume_record.data[0]['id']

        text = extract_text_from_pdf(file_bytes)
        extracted_skills = extract_skills(text)
        years_exp = extract_years_of_experience(text)

        supabase.table("resume_analysis").insert({
            "resume_id": resume_id,
            "skills_extracted": extracted_skills,
            "experience_years": years_exp
        }).execute()

        target_job_title = "Software Engineer"
        mock_required = ["Python", "SQL", "React", "Git"]
        score_data = calculate_ats_score(text, extracted_skills, mock_required, years_exp)
        missing_skills = [s for s in mock_required if s.lower() not in [es.lower() for es in extracted_skills]]
        suggestions = generate_improvement_suggestions(missing_skills, target_job_title)

        supabase.table("ats_scores").insert({
            "resume_id": resume_id,
            "score": score_data["score"],
            "keyword_match": score_data["keyword_match"],
            "formatting_score": score_data["formatting_score"],
            "suggestions": suggestions
        }).execute()

        jobs_html = ""
        if score_data["score"] >= 60:
            all_jobs = supabase.table("jobs").select("*").execute().data
            for job in all_jobs:
                req_skills = job.get('required_skills', [])
                if req_skills:
                    overlap = len([s for s in req_skills if s.lower() in [es.lower() for es in extracted_skills]])
                    job['match_percent'] = int((overlap / len(req_skills)) * 100)
                else:
                    job['match_percent'] = 0
            ranked_jobs = sorted(all_jobs, key=lambda x: x['match_percent'], reverse=True)
            jobs_html = templates.get_template("partials/job_list.html").render({"jobs": ranked_jobs, "request": request})

        external_roles = get_recommended_roles(extracted_skills, top_n=3)
        for role in external_roles:
            q = quote_plus(role['title'])
            role['links'] = {
                'LinkedIn': f"https://www.linkedin.com/jobs/search/?keywords={q}",
                'Indeed':   f"https://www.indeed.com/jobs?q={q}",
                'Naukri':   f"https://www.naukri.com/{role['title'].replace(' ', '-')}-jobs",
                'Glassdoor':f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={q}",
                'Google Jobs': f"https://www.google.com/search?q={q}+jobs&ibp=htl;jobs",
                'Internshala': f"https://internshala.com/internships/keywords-{q}"
            }

        external_jobs_html = templates.get_template("partials/external_jobs.html").render(
            {"roles": external_roles, "request": request}
        )

        return templates.TemplateResponse("partials/score_result.html", {
            "request": request,
            "score": score_data["score"],
            "suggestions": suggestions,
            "jobs_html": jobs_html,
            "external_jobs_html": external_jobs_html,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(content=f"<div class='text-red-400 p-4 bg-red-900/30 border border-red-800 rounded-xl'><b>Error:</b> {str(e)}</div>")

@app.post("/api/chat", response_class=HTMLResponse)
async def api_chat(request: Request, message: str = Form(...), user: dict = Depends(get_current_student)):
    try:
        user_id = user['user'].id
        user_name = user.get('name', 'Student')
        
        # 1. Fetch user's latest resume, analysis, and ATS score
        context = ""
        try:
            resume_res = supabase.table("resumes").select("id, storage_path").eq("student_id", user_id).order("uploaded_at", desc=True).limit(1).execute()
            if resume_res.data:
                resume_id = resume_res.data[0]['id']
                storage_path = resume_res.data[0].get('storage_path')
                
                # Fetch skills & experience
                skills: list[str] = []
                years_exp = 0
                analysis = supabase.table("resume_analysis").select("*").eq("resume_id", resume_id).execute()
                if analysis.data:
                    skills = analysis.data[0].get('skills_extracted', [])
                    years_exp = analysis.data[0].get('experience_years', 0)
                
                # Fetch latest ATS score
                ats_score = "N/A"
                ats_data = supabase.table("ats_scores").select("score, suggestions").eq("resume_id", resume_id).execute()
                if ats_data.data:
                    ats_score = str(ats_data.data[0].get("score", "N/A"))
                
                # Download full resume text from Supabase storage
                resume_text = ""
                if storage_path:
                    try:
                        file_data = supabase.storage.from_("resumes").download(storage_path)
                        resume_text = extract_text_from_pdf(file_data)
                    except Exception:
                        pass
                
                resume_excerpt = resume_text[:3000] if resume_text else "No raw text available."
                context = (
                    f"Candidate Name: {user_name}\n"
                    f"Identified Skills: {', '.join(skills) if skills else 'None'}\n"
                    f"Experience: {years_exp} years\n"
                    f"Latest ATS Score: {ats_score}/100\n"
                    f"Full Resume Content Excerpt:\n{resume_excerpt}\n"
                )
        except Exception as e:
            print(f"Error fetching resume context for chat: {e}")
            context = ""

        # 2. Call Gemini with multi-model fallback chain
        google_api_key = os.environ.get("GOOGLE_API_KEY")
        if not google_api_key:
            ai_msg = "Google API Key is not configured."
        else:
            prompt = (
                "You are SkillSync AI, an expert, supportive, and practical career coach.\n"
                f"Candidate Resume Details:\n{context if context else 'No resume uploaded yet.'}\n\n"
                f"Candidate Question: \"{message}\"\n\n"
                "Instructions:\n"
                "- If the candidate has uploaded a resume, answer specifically referencing their actual skills, projects, and experience.\n"
                "- Keep your answer concise, structured, and actionable (1-2 clear paragraphs or bullet points).\n"
                "- Provide encouraging, industry-standard career advice."
            )
            
            # pyrefly: ignore [missing-import]
            from google import genai
            client = genai.Client(api_key=google_api_key)
            
            MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-flash-latest", "gemini-3.6-flash"]
            ai_msg = None
            
            for model_name in MODELS:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    parts: list[str] = []
                    if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                        for p in response.candidates[0].content.parts:
                            p_text = getattr(p, "text", None)
                            if p_text:
                                parts.append(str(p_text))
                    result = "".join(parts).strip()
                    if result:
                        ai_msg = result
                        break
                except Exception as model_err:
                    print(f"Model {model_name} attempt: {model_err}")
                    continue
                    
            if not ai_msg:
                ai_msg = "I'm having trouble connecting right now. Please try asking again in a moment."

        html = f"""
        <div class="w-full flex justify-end">
            <div class="bg-[#1C1C1F] border border-white/[.08] text-white p-3 rounded-lg text-sm inline-block max-w-[85%] text-left">
                {message}
            </div>
        </div>
        <div class="w-full flex justify-start">
            <div class="bg-brand-500/10 border border-brand-500/20 text-brand-100 p-3 rounded-lg text-sm inline-block max-w-[85%]">
                {ai_msg}
            </div>
        </div>
        """
        return HTMLResponse(content=html)
    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(content=f"<div class='w-full flex justify-start'><div class='bg-red-900/30 text-red-400 border border-red-800 p-3 rounded-lg text-sm inline-block max-w-[85%]'>Error: {str(e)}</div></div>")

@app.post("/api/jobs/{job_id}/apply", response_class=HTMLResponse)
async def apply_to_job(request: Request, job_id: str, user: dict = Depends(get_current_student)):
    try:
        supabase.table("applications").insert({
            "student_id": user['user'].id,
            "job_id": job_id,
            "status": "Applied"
        }).execute()
        return HTMLResponse(content="<button disabled class='w-full bg-green-500/20 border border-green-500/40 text-green-400 py-2.5 rounded-xl font-medium cursor-not-allowed text-sm'>✓ Applied</button>")
    except Exception as e:
        return HTMLResponse(content="<div class='text-red-400 text-sm'>Failed to apply</div>")

@app.post("/api/applications/{app_id}/status", response_class=HTMLResponse)
async def update_application_status(request: Request, app_id: str, status: str = Form(...), user: dict = Depends(get_current_admin)):
    try:
        supabase.table("applications").update({"status": status}).eq("id", app_id).execute()
        full_data = supabase.table("applications").select(
            "id, status, applied_at, students(name), jobs(title)"
        ).eq("id", app_id).execute().data[0]
        return templates.TemplateResponse("partials/application_row.html", {"request": request, "app": full_data})
    except Exception as e:
        return HTMLResponse(content="<div class='text-red-400 text-sm'>Error updating status</div>")

@app.post("/api/jobs")
async def create_job(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    skills: str = Form(...),
    location: Optional[str] = Form(None),
    salary: Optional[str] = Form(None),
    user: dict = Depends(get_current_admin)
):

    try:
        skills_list = [s.strip() for s in skills.split(",") if s.strip()]
        salary_num  = float(salary) if salary else None

        companies = supabase.table("companies").select("id").limit(1).execute().data
        if not companies:
            comp_res = supabase.table("companies").insert({"name": "Default Company"}).execute()
            company_id = comp_res.data[0]['id']
        else:
            company_id = companies[0]['id']

        supabase.table("jobs").insert({
            "company_id":      company_id,
            "title":           title,
            "description":     description,
            "required_skills": skills_list,
            "location":        location,
            "salary":          salary_num,
            "posted_by":       user['user'].id
        }).execute()

        return RedirectResponse(url="/admin", status_code=302)
    except Exception as e:
        return HTMLResponse(content=f"<div class='text-red-400 p-3 rounded-xl bg-red-900/20 border border-red-800/40 text-sm'>Error: {str(e)}</div>")
