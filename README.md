# Room Rental Platform

FastAPI backend and React frontend for public room search, landlord listing management, tenant enquiries, and platform moderation.

## Run locally

Configure `backend/.env` and `frontend/.env` using their `.env.example` files. Keep local frontend API requests pointed at your local backend (leave `VITE_API_BASE_URL` empty to use Vite's proxy to port 8001).

In two PowerShell terminals, from the repository root:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

```powershell
Set-Location frontend
npm install
npm run dev -- --host 127.0.0.1
```

## Rental workflows

Sign in with the appropriate account role. Navigation links appear in each role's dashboard.

Workspace pages retain the role's navigation and signed-in account. Landlord sections use URLs such as `/landlord?view=listings` and `/landlord?view=enquiries`; refreshing or using browser Back preserves the selected section. Tenant dashboard tabs use the same `?view=` convention. An enquiry's Messages link opens its specific conversation, and choosing another conversation updates the URL.

| Location | Features |
| --- | --- |
| `/landlord` | Live business metrics, monthly enquiries, conversion summary, and listing availability controls. |
| `/landlord/leads` | Enquiry progress, viewing stages, rental and unsuccessful outcomes, and internal progress history. |
| `/landlord/verification` | Identity/property authorization requests, administrator feedback, resubmission, and private trust summaries for your own properties. |
| `/landlord/reports` | Report an account or listing and follow report status. |
| `/tenant/leads` | Enquiry progress and history, with inaccurate-progress dispute submission. |
| `/admin/verification` | Review private supporting statements, approve/reject/request information, and inspect audit history. |
| `/admin/leads` | Inspect leads and progress history. |
| `/admin/disputes` | Review disputes, correct the conversion stage or dismiss a dispute with a reason. |
| `/admin/reports` | Report assignment, resolution/dismissal, internal notes, and audit history. |
| `/listings/{id}` | Public room details. Landlord/property trust summaries are not displayed here. |

Availability is separate from moderation and lead outcomes. Recording a rental does not automatically mark a room occupied; landlords update availability in Listings. Lead updates pause during an open dispute. Phone verification uses the existing WhatsApp integration; no new phone-verification UI is included here.

## Checks

```powershell
Set-Location frontend
npm run build
```

Backend checks excluding WhatsApp:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --ignore-glob=tests/test_whatsapp*.py
```

### Browser checks with synthetic data

The Playwright suite uses installed Google Chrome and a disposable PostgreSQL database. It runs its own backend on port 8017 and frontend on port 5187, and does not reuse running application servers. The fixture script refuses any database other than `room_rental_frontend_e2e` on `127.0.0.1:55433`, and refuses a database that already contains tables.

From the repository root, with Docker running and backend/frontend dependencies installed:

```powershell
docker run --detach --rm --name room-rental-frontend-e2e --env POSTGRES_PASSWORD=local-browser-check-only --env POSTGRES_DB=room_rental_frontend_e2e --publish 127.0.0.1:55433:5432 postgres:17-bookworm
$env:E2E_DATABASE_URL = 'postgresql+psycopg://postgres:local-browser-check-only@127.0.0.1:55433/room_rental_frontend_e2e'
backend/.venv/Scripts/python.exe backend/tests/seed_frontend_e2e.py
Set-Location frontend
npm run test:e2e
docker stop room-rental-frontend-e2e
```

Wait for PostgreSQL to accept connections before seeding. Use a fresh disposable container for a full rerun because the browser scenarios persist their changes. Test accounts and passwords are synthetic and exist only in that database. Tests cover real login, availability persistence, lead transitions/outcomes, dispute review, verification/resubmission, owner-only trust summaries, request retries, permissions, mobile layout, and report notes.

Pushing `feature/authentication` triggers Azure deployment. Local builds and tests do not deploy the application or confirm the Google Maps key's production referrer restrictions.

The active workflows deploy the frontend to Azure Static Web Apps and the backend to `room-rental-api`. The obsolete `room-rental` deployment is retained in `.github/archived-workflows/`; it is outside GitHub Actions' active workflow directory and does not run on pushes.
