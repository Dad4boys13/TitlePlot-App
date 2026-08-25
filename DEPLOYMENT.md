# Deployment Guide — Title Report Easement Plotter (Backend)

Goal of this first deployment: get the app running somewhere with real
internet access so we can finally test the two open assumptions —
hyperlink auto-fetch and the GIS parcel lookup — against reality
instead of guessing further.

This guide uses **Render**, since it deploys straight from a Dockerfile
with no extra config. Railway is a near-identical alternative noted at
the bottom if you'd rather use that instead.

---

## 0. What you need before starting

- The `titleplot_app` codebase (from the zip delivered earlier)
- A GitHub account (Render deploys from a git repo)
- A Render account (free to sign up, no card required for this tier)

---

## 1. Push the code to GitHub

```bash
cd titleplot_app
git init
git add .
git commit -m "Initial backend prototype"
```

Create a new **empty** repo on GitHub (no README/license, to avoid a
merge conflict), then:

```bash
git remote add origin https://github.com/<your-username>/titleplot-app.git
git branch -M main
git push -u origin main
```

---

## 2. Create the Render service

1. Go to [render.com](https://render.com) → **New +** → **Web Service**
2. Connect your GitHub account, select the `titleplot-app` repo
3. Render should auto-detect the `Dockerfile` at the repo root. If it
   asks you to choose a runtime/environment, choose **Docker**.
4. Settings:
   - **Name**: `titleplot-app` (or anything)
   - **Region**: closest to you (doesn't matter functionally yet)
   - **Instance type**: the free tier is fine for this smoke test
   - **Environment variables**: none required yet — the app has no
     auth or database wired in at this stage
5. Click **Create Web Service**

Render will build the Docker image (this installs `tesseract-ocr` and
`poppler-utils` per the Dockerfile, plus the Python deps) and deploy
it. First build typically takes 3-5 minutes. Watch the build log for
errors — the most likely failure mode at this stage is a missing
package version; if `pip install` fails on something, paste the error
back and we'll fix `requirements.txt`.

When it's done, Render gives you a public URL like:
`https://titleplot-app.onrender.com`

---

## 3. Smoke-test it — this is the part that actually matters

### 3a. Health check
```bash
curl https://titleplot-app.onrender.com/health
```
Expect: `{"status":"ok"}`

### 3b. The big one: GIS parcel lookup (never tested until now)
```bash
curl "https://titleplot-app.onrender.com/parcels/lookup?apn=146-551-21"
```
Three possible outcomes:
- **Real polygon geometry comes back** → the statewide GIS layer works. Note whether the boundary looks like straight segments (fine as-is) or you can tell it's simplified/inaccurate near the curved frontage (expected next step: compare vertex count/shape to the recorded map).
- **404 "No parcel found"** → try without dashes (`14655121`) or confirm the APN format the layer expects; may need a different `where` clause.
- **500 / connection error** → the service may be unreachable from Render's network, rate-limited, or the endpoint path/params changed since this was written — paste the error back.

### 3c. Schedule B parsing, end to end with a real file
```bash
curl -X POST https://titleplot-app.onrender.com/reports/parse \
  -F "file=@/path/to/Prelim_Package.pdf"
```
Expect: JSON with `hyperlinks` (should list the 11 embedded links we
found earlier) and `schedule_b_items` (should show Items 7/9/10/11 as
plottable with parsed clauses, matching what we validated locally).

### 3d. The full build endpoint
```bash
curl -X POST https://titleplot-app.onrender.com/plats/build \
  -F "apn=146-551-21" \
  -F "county=Orange" \
  -F "front_compass=N" \
  -F "file=@/path/to/Prelim_Package.pdf" \
  --output plat.svg
```
Open `plat.svg` in a browser. This is the true end-to-end test.

### 3e. The hyperlink-fetch question — needs new code, not yet in this build
Note: nothing deployed yet actually *downloads* the linked exhibits
(tract map, easement grants) — `pdf_ingest.py` only extracts the link
*targets* (the URLs), it doesn't fetch them. That fetch step is the
next piece to write once you confirm (via your own curl/incognito test
from earlier) whether those Qualia links are truly anonymous-accessible.
If they are, the fetch code is a small addition (`requests.get(uri)`
per extracted link, saving the result, then feeding it through the
same `extract_text` / parsing path already built). Say the word once
you have that confirmation and I'll add it.

---

## 4. What to bring back from this test

Whichever of 3b/3c/3d don't work as expected — paste the actual error
response back here. That's real signal, not more speculation, and lets
us fix the specific thing that's actually broken rather than guessing
at it in the abstract.

---

## Alternative: Railway

Nearly identical flow:
1. [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Railway also auto-detects the Dockerfile
3. Same env vars (none needed yet)
4. Railway assigns a public domain under Settings → Networking → Generate Domain
5. Same smoke tests as above, just swap the base URL

Both are cheap-to-free for this stage and easy to migrate away from
later since nothing here is platform-specific.
