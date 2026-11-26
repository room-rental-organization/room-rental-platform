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

## Listing data and caching

The landing page and its Explore/list/map views share a TanStack Query infinite query. `GET /api/v1/listings/search` returns eight recent approved, active, available rooms initially, then explicit pages through **Load more rooms**. Search, rent, room type, amenities and availability filters run in SQL before pagination. Supported sorting is `recent` or `rent_asc`; ties use listing ID. `limit` is bounded at 50 and `offset` at 100000. Offset pages may shift under concurrent writes; refreshing reloads them, and the frontend removes duplicate IDs. Card responses contain a description preview and one cover photo. Full details use their own query and schema; a partial card never populates the detail cache.

Frontend freshness/retention defaults:

| Resource | Fresh for | Retained while inactive |
| --- | --- | --- |
| Public listing pages | 60 seconds | 15 minutes |
| Room detail | 30 seconds | 10 minutes |
| Areas and amenities | 30 minutes | 60 minutes |
| Private resources | 30 seconds | 5 minutes |

Window-focus refetching is disabled. Freshness expiration does not itself start a timer-driven request; stale queries refresh when observed again or explicitly refreshed/invalidated. Search changes debounce for 350 ms and radius selection for 300 ms. List/map switches, filter-panel expansion and map panning do not fetch the listing collection. The map shows the loaded result pages. There is no viewport request to debounce. Place-ID-only locations still use the existing provider lookup with approximate coordinates and `no-store`; no Google coordinates are persisted or added to the server response cache. Radius search remains the compatibility path and can still involve provider lookups across eligible rooms.

Successful mutations invalidate related server state. Landlord, tenant and admin listing resources, shared rental panels and catalogs reuse query data. Private cache keys contain a session generation, never the bearer token. Login/account changes and logout cancel/remove private queries and clear mutation data; delayed results and cache setters cannot populate the next session. The cache is in memory only, without browser persistence. Authentication, messages, notifications and provider map-location responses use live requests.

The backend uses cache-aside in `app/services/public_listing_reads.py` with a `PublicCache` protocol and a thread-safe in-memory implementation. Entries contain serialized validated public schemas, never SQLAlchemy instances. Keys include the projection/version, pagination, filters and sort. Identical misses share one loader; unrelated misses can run concurrently. ORM listing, photo, amenity-link, area and moderation changes invalidate after the outer transaction commits, including assistant workflows that defer their commit. A rollback does not invalidate, and an in-flight response from an earlier cache generation cannot repopulate it. Business eligibility checks for saving rooms, enquiries and reports always read the database.

Optional backend settings (defaults require no Azure configuration changes):

```dotenv
PUBLIC_CACHE_TTL_SECONDS=30
PUBLIC_CACHE_MAX_ENTRIES=128
PUBLIC_CACHE_MAX_BYTES=4194304
```

The byte limit applies to serialized payloads. Oversized responses are served without caching. The original array endpoint remains compatible with older deployed clients and is cached for non-radius reads; new discovery uses the paged endpoint. Private data and authentication are never stored in this public cache.

Each API worker has its own cache. App Service restarts/idle unloading clear it; writes in another worker or direct SQL changes are reflected after TTL expiry. For multiple workers with immediate shared invalidation, replace the protocol implementation with Redis/shared invalidation. This change adds no paid service, migration or background worker. Existing workflows remain usable. During a frontend-first rollout against an older backend, discovery temporarily falls back to a cached legacy array and pages/filters it locally; normal validation/server failures are not swallowed. Deploying the additive backend first avoids this temporary full-collection compatibility read. Once the backend is updated, subsequent query refreshes use SQL pagination.

Application INFO logs include `public_cache` hit/miss/invalidation events and `api_performance` route-template, status, duration and statement/SELECT counts. They omit SQL text, parameters, bearer tokens, search terms, coordinates and user IDs. SQLAlchemy parameter display is disabled. To see these application records under Uvicorn, configure application loggers/handlers at INFO; `--log-level info` alone may only configure Uvicorn's own loggers.

Reproduce query counts with synthetic in-memory SQLite data (24 rooms: 12 approved, six unapproved active, six drafts; six saved rooms):

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider tests/test_public_listing_reads.py -k query_count_comparison
```

| Operation | Before SELECTs | After cold read | After cache hit |
| --- | --- | --- | --- |
| Public discovery | 4, returning all 12 eligible rooms | 3, returning 8 rooms | 0 |
| Room details | 4 | 3 | 0 |
| Six saved rooms | 25 | 4 | Private response not in server cache |

These counts exclude authentication and connection health checks and do not measure Neon latency. Browser tests assert one listing-page request across list/map/filter-panel interactions and return navigation, one detail request across repeated visits, and one search request for rapid typing. Cold visitors still make HTTP requests; repeat visitors hitting a warm API cache avoid listing SQL queries.

No index migration is included. The eligible-room query uses a latest-moderation scalar subquery, and cover photos/amenities are batched. Candidate PostgreSQL indexes to evaluate with representative `EXPLAIN (ANALYZE, BUFFERS)` plans are moderation `(listing_id, decided_at DESC, moderation_id DESC)`, photos `(listing_id, photo_id)`, and a partial listing index on `(created_at DESC, listing_id DESC)` for active/available rooms. Confirm existing Neon indexes and actual plans before adding overlapping indexes; synthetic SQLite counts cannot establish PostgreSQL index needs.
