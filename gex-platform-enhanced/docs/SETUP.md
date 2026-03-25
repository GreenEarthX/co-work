# GreenEarthX Platform — Setup Guide

## Prerequisites

- **Node.js** 20+
- **Python** 3.11+
- **npm** 10+

> Docker/PostgreSQL/Redis are not required for local development. The platform runs on SQLite by default.

---

## Local Development (Recommended)

### Step 1 — Finance Engine (port 8001)

```bash
cd gex_pf_engine/backend

# First time: create venv and install
python -m venv ../micro_service
source ../micro_service/bin/activate     # Windows: ..\micro_service\Scripts\activate
pip install -r requirements.txt

# Start
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Verify: `http://localhost:8001/docs`

### Step 2 — Platform Backend (port 8000)

```bash
cd gex-platform-enhanced/backend

# First time: create venv and install
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify: `http://localhost:8000/docs`

### Step 3 — Frontend (port 3000)

```bash
cd gex-platform-enhanced/frontend
npm install
npm run dev
```

Open: `http://localhost:3000`

On first visit, the **RoleSelector** will prompt you to set your company type, service type, and business function. This controls which navigation items are visible.

---

## Environment Variables

Create `gex-platform-enhanced/backend/.env`:

```bash
ENVIRONMENT=development
DATABASE_URL=sqlite:///./greenearth.db
CORS_ORIGINS=["http://localhost:3000"]
SECRET_KEY=dev-secret-key-change-in-prod
```

The backend falls back to sensible defaults if `.env` is absent.

---

## First-Run Seed Data

Seed bankability evidence for a demo project:

```bash
curl -X POST "http://localhost:8000/api/v1/bankability/evidence/seed?project_id=default"
```

---

## CISO Administration

The CISO gear icon (⚙) in the top-bar requires a password. Default: `Enter-123`.

To override, set in browser console:

```js
localStorage.setItem('gex_ciso_password', 'your-password')
```

Session is maintained via `sessionStorage` — re-authentication required on new tab/window.

---

## Key URLs

| URL | Description |
| --- | --- |
| `http://localhost:3000` | Frontend |
| `http://localhost:3000/onboarding` | Role selector + project wizard |
| `http://localhost:8000/docs` | Platform API (Swagger) |
| `http://localhost:8001/docs` | Finance Engine API (Swagger) |
| `http://localhost:8000/health` | Platform health check |
| `http://localhost:8001/health` | Finance Engine health check |

---

## Docker (Optional)

```bash
cd gex-platform-enhanced
docker-compose up -d
```

Services: `frontend` (3000), `backend` (8000), `redis` (6379).
The finance engine runs separately — start it manually per Step 1 above.

---

## Troubleshooting

**Frontend shows blank page after navigation:**
Ensure React Router routes match — all finance routes are available under both `/stage-gates` (legacy) and `/finance/stage-gates` (new).

**Backend import errors on startup:**
Optional modules (Redis, event bus, Matrix) are wrapped in `try/except`. The warning `⚠️ module not found — skipping` is normal in minimal installs.

**CISO gear doesn't open dropdown:**
After authenticating, the CISO session is stored in `sessionStorage`. Opening a new tab requires re-authentication.
