# Putting Relay online

Same shape as Tally: the **API** on Google Cloud Run, the **page** on Vercel.

## 1. Draft the demo emails ahead of time (once, from your computer)

```powershell
python -m relay.prepare
```
The agent drafts all 60 demo emails (5 to 8 minutes), so visitors see results instantly.

## 2. The API on Cloud Run

```powershell
copy deploy.env.example.yaml deploy.env.yaml
notepad deploy.env.yaml          # DATABASE_URL and GROQ_API_KEY: the same values as in .env
gcloud run deploy relay --source . --region us-west1 --allow-unauthenticated `
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 2 --concurrency 10 --timeout 120 `
  --cpu-boost --env-vars-file deploy.env.yaml
```
Check `<Service URL>/health` says `"status":"ok"`.

| Option | Why |
| --- | --- |
| `--timeout 120` | A test email runs the whole agent (sort, lookups, draft, checks): usually 5 to 15 seconds. |
| `--concurrency 10` | Each request may hold a database connection; Supabase's free pooler allows only a few at once. |
| `--min-instances 0` | Free when idle; the first request after a quiet spell takes a few extra seconds. |

## 3. The page on Vercel

1. Push the repo to GitHub.
2. Vercel → **Add New → Project** → import `relay` → **Root Directory** `web`.
3. **Environment Variables** (type **Config**, all environments): `NEXT_PUBLIC_API_URL` = the Cloud Run URL.
4. **Deploy**.

## 4. Let the page call the API

In `deploy.env.yaml`: `ALLOWED_ORIGINS: "https://YOUR-RELAY.vercel.app,http://localhost:3000"` (no `/` at the
end), then run the `gcloud run deploy` command again. `<API URL>/health` lists the allowed addresses.

## 5. Gmail (optional, for a demo on a real inbox)

See [automation/README.md](automation/README.md).

## If something's wrong

| What you see | Likely cause |
| --- | --- |
| "Couldn't reach Relay's server" | `/health` doesn't list the page's exact address in `allowed_origins`, or `NEXT_PUBLIC_API_URL` is wrong on Vercel. |
| Demo emails show no draft | Step 1 wasn't run; run `python -m relay.prepare`. |
| "The agent couldn't process that email" | `GROQ_API_KEY` missing or Groq's limit reached: check the logs. |
| Logs | `gcloud run services logs read relay --region us-west1 --limit 50` |
