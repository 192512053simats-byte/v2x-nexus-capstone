# Deploy V2X Nexus on Render (free hosting)

This application is **not** a static website: `/api/run` executes a Python simulation. GitHub Pages alone cannot host it. Use a Render **Web Service**.

## 1 — Put the project on GitHub

1. Create a GitHub account or sign in at https://github.com.
2. Choose **New repository** and name it `v2x-nexus-capstone`. Choose Public or Private as preferred.
3. Extract the deploy-ready ZIP. Open the extracted `v2x-command-center` folder.
4. In the new GitHub repository click **uploading an existing file** or **Add file → Upload files**.
5. Upload **the contents of `v2x-command-center`**, not the ZIP and not only the outer folder. `render.yaml`, `app.py`, `requirements.txt`, `engine.py`, `ai_model.py`, `templates/`, and `static/` must all be in the repo root. Commit the files.

If you already use Git, you can instead push the extracted folder to your repository normally.

## 2 — Deploy on Render

1. Visit https://dashboard.render.com, create or sign into your Render account, and connect GitHub.
2. Click **New → Web Service**; select your `v2x-nexus-capstone` repository.
3. Choose **Python 3** for runtime and **Free** for the instance type.
4. Settings (Render might auto-detect these from `render.yaml` if you use **New → Blueprint** instead):
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --workers 1 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT app:app`
   - Health check path: `/api/health`
   - Optional environment variable: `PYTHON_VERSION` = `3.11.11`
5. Click **Deploy Web Service**. If you prefer the automatic configuration, choose **New → Blueprint**, connect the repository, and use the included `render.yaml`.
6. When the deploy completes, visit the public `https://...onrender.com` URL provided by Render. Check `https://YOUR-RENDER-DOMAIN/api/health` as well; `status` should be `ok`.
7. On the dashboard, click **Run Comparison** and verify that the charts update.

## 3 — Troubleshooting

- **ModuleNotFoundError: gunicorn / flask / sklearn** — check that `requirements.txt` is at the repository root and the build command is correct.
- **Port scan failed or app won't start** — use the Gunicorn command shown above, **not** `python server.py`, which binds to 127.0.0.1 and is for local access only.
- **404 on CSS/JS** — ensure you uploaded both the `static` and `templates` directories with their contents.
- **Health check slow** — first `/api/health` can train the small synthetic-label Random Forest; it then caches the model in memory.
- **AI shows heuristic** — check deployment logs for failed `scikit-learn` installation. The heuristic is a fallback, not the trained ML variant.
- **Slow loading after inactivity** — Render's free web services sleep after 15 minutes idle and wake on demand, which can take roughly a minute.
- **Insufficient memory or slow requests** — lower the number of concurrent visitors and avoid running many high-density simulations at once. Upgrade the compute plan only if necessary.

## Important research limitations

This is a public-facing simulator prototype, not a real ns-3 or 6G stack. It generates synthetic positions, hazards, traffic and wireless outcomes. It supports optional **offline SUMO trace imports** only if you bundle `data/sumo_trace.json` into the repo (it is excluded by the original `.gitignore`). Render cannot run a full local SUMO installation automatically with this configuration. There is no per-user session database or authentication; the API is accessible publicly.

## Hosting costs and privacy

Render offers a free tier subject to monthly usage and resource caps. Check Render's current terms before deploying. Avoid publishing private datasets, API keys, or personal credentials. The included app has no authentication, so anyone with the URL can run experiments and consume your shared hosting resources.
