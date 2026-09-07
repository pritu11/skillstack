# SkillStack

A simple freelance career platform with login/signup, a small backend API, and a polished landing page.

## Run locally

```bash
python3 app.py
```

Then open http://127.0.0.1:8000/

## Deploy to Vercel

1. Push this repository to GitHub.
2. Import it in Vercel.
3. Vercel will serve the static site and the API routes automatically.

## Connect Supabase

1. Create a Supabase project.
2. Open the SQL Editor and run `supabase_schema.sql`.
3. Add these Vercel environment variables for all environments:
	- `SUPABASE_URL`: Project URL from Supabase settings.
	- `SUPABASE_KEY`: Supabase service-role key.
	- `SKILLSTACK_TOKEN_SECRET`: A long random secret.
4. Redeploy the Vercel project.

Without these variables, local development uses the JSON files in `data/`. To reset local demo data to 40 users and 40 leads, run:

```bash
python3 seed_data.py
```
