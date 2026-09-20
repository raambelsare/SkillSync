# AI Resume Analyzer + Placement Portal

A college field project built with FastAPI, HTMX, Tailwind CSS, and Supabase.

## Features
- Supabase Auth (Student & Admin roles)
- Resume PDF Upload & Parsing
- ATS Scoring (Formatting + Keyword Matching)
- AI Resume Improvement Suggestions (Google Gemini API)
- Job Listings & Recommendations
- Admin Application Management

## Tech Stack
- **Backend:** FastAPI (Python 3.11+)
- **Database/Auth/Storage:** Supabase
- **Frontend:** Jinja2 + HTMX + Tailwind CSS (CDN) + Three.js (Landing page only)
- **AI:** Google Gemini API
- **Deployment:** Vercel (Python Serverless Runtime)

## Deploy to Vercel

1. **Supabase Setup:**
   - Create a Supabase project.
   - Run the SQL migration from the spec in the Supabase SQL editor.
   - Create a `resumes` storage bucket (private, with RLS policies scoped to each student's own files).

2. **Gemini Setup:**
   - Get a Google Gemini API key from [Google AI Studio](https://aistudio.google.com).

3. **Vercel Deployment:**
   - Import this repository to Vercel.
   - Add the following environment variables in Vercel's project settings:
     - `SUPABASE_URL`
     - `SUPABASE_ANON_KEY`
     - `SUPABASE_SERVICE_ROLE_KEY`
     - `GOOGLE_API_KEY`
   - Run `vercel deploy`. Vercel will use `vercel.json` to build `api/index.py` as a Python serverless function.
