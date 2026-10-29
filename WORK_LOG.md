# 🧾 Work Log: Dashboard (backend + frontend)

**Author:** Karim Mohamed
**Scope:** the web dashboard only: the frontend ([dashboard/](dashboard/)) and its backend API ([backend/](backend/)).
My Snowflake + Airbyte setup (stopped at step 5c, when the team moved to `SUPPLYCHAIN_DW`) is in [PIPELINE_WORK_LOG.md](PIPELINE_WORK_LOG.md).

**How I document each step (team rules from [Notion_Documentation.md](Notion_Documentation.md)):**
1. Write the step right after I finish it.
2. Each step = **what I did** (1–3 lines) + **screenshot** + **code** (if any).
3. Never show passwords, keys or tokens. Use `<YOUR_KEY>` and blur screenshots.

Status: ✅ done · ⏳ in progress · ⬜ not started

---

## Web dashboard (frontend) ⏳
> **Update 2026-10-29:** the mock data source (fake numbers + in-browser simulator) described in this entry was removed. The dashboard now reads only the backend. See "Mock data removed" below.

**What I did (2026-10-26):** Built [dashboard/](dashboard/): React + Vite + Tailwind, Recharts for KPI charts, Three.js (react-three-fiber) for the 3D map. All 7 dashboards from the catalog plus a Live Fleet Map. Data is mocked behind one switchable data source, so the real backend plugs in later without touching the pages. Details: [dashboard/README.md](dashboard/README.md).

**Logic:**
- Pages → hooks (`useKpis`, `useStream`) → `dataSource` → `mock` or `api` (chosen by `VITE_DATA_SOURCE`). Since 2026-10-29: `api` only, no switch.
- Warehouse KPIs come pre-calculated (`GET /kpis/{dashboard}`). The frontend does no KPI math.
- Live data comes over SSE (`telemetry` and `reefer` batches, `alert` rows) with the catalog column names.
- The mock simulator moves 5,000 trucks on 108 lanes and injects the 4 anomaly families.

**Tests done:** `vite build` passes. A headless check confirmed that all 8 dashboards return their KPIs and series, the simulator emits 5,000 telemetry plus about 2,500 reefer rows per tick, and all 4 anomaly types appear (about 50 active at once). The dev server serves all pages. Not yet checked: visual check in a browser.

---

## Backend API (FastAPI → Snowflake + Kafka) ✅
**What I did (2026-10-28):** Built [backend/](backend/): FastAPI that logs in to Snowflake with username + password from `backend/.env` and answers `GET /health` (who am I in Snowflake) and `GET /api/tables` (tables and views the user can see, with row counts). Details and run steps: [backend/README.md](backend/README.md).
The Snowflake it will query is a **second account owned by a teammate** (not `RSGNWLJ-PK32132`). The owner sends account identifier, user, password, database (and optionally role, warehouse, schema); they go into `backend/.env` only.

**Decisions (2026-10-28):** password login only · first scope = connection + health + table listing · `backend/` next to `dashboard/`, API only (Vite dev server calls `http://localhost:8000/api`, CORS allows `http://localhost:5173`).

**Logic:** `main.py` routes → `snowflake_client.fetch_all(sql)` (one shared connection, reopened if Snowflake closes it) → `config.settings` (reads `backend/.env` once). Any Snowflake error becomes HTTP 503 with the Snowflake message.

**Files:** `backend/.env.example`, `backend/requirements.txt`, `backend/README.md`, `backend/app/{__init__,config,snowflake_client,main}.py`. Packages installed into the shared `.venv`: `fastapi`, `uvicorn`, `pydantic-settings` (`snowflake-connector-python` was already there).

**Tests done:** without `backend/.env` the app stops at startup listing the missing variables ✅ · server starts, `/docs` shows `/health` and `/api/tables` ✅ · with a fake account `/health` returns 503 `Snowflake error: 250001 (08001): Failed to login ...` ✅ · CORS preflight from `http://localhost:5173` returns 200 ✅.
**Real login (2026-10-29) ✅:** owner's account `QGAUKSF-CF11950`, user `AIRFLOW_USER` (role `AIRFLOW_ROLE`), database `SUPPLYCHAIN_DW`, schema `DBT_MARTS`. First `/api/tables` call failed with `000606: No active warehouse selected` because the user has no default warehouse. `SHOW GRANTS TO ROLE AIRFLOW_ROLE` shows `USAGE` on `AIRBYTE_WH` only, so `SNOWFLAKE_API_WAREHOUSE=AIRBYTE_WH` was set in `backend/.env`. After that `/health` and `/api/tables` return 200.

**Tables seen in `SUPPLYCHAIN_DW.DBT_MARTS` (row counts on 2026-10-29):** `DIM_CUSTOMER` 2,500 · `DIM_DATE` 1,034 · `DIM_DRIVER` 10,366 · `DIM_FACILITY` 50 · `DIM_LOCATION` 25 · `DIM_ROUTE` 116 · `DIM_TRAILER` 7,500 · `DIM_TRUCK` 5,000 · `FCT_DELIVERY_EVENTS` 1,909,128 · `FCT_FUEL_PURCHASES` 1,852,581 · `FCT_MAINTENANCE` 106,524 · `FCT_SAFETY_INCIDENTS` 2,422 · `FCT_SHIPMENTS` 953,716 · `FCT_TRIPS` 953,293. The role also reads `RAW_DATA` (13 tables, 1k to 7.7M rows). `FCT_MAINTENANCE` and `FCT_SAFETY_INCIDENTS` were not in the list the owner sent.

### KPI validation endpoint ✅ (2026-10-29)
**What I did:** Added `GET /api/kpis/validation`. It calculates two KPIs that need joins on `DBT_MARTS` over all rows, and returns each value with join checks (rows matched / unmatched, used vs full-table totals), to prove the model joins work.

**Decisions:** KPI 9 Distance Variance + KPI 28 Margin Proxy · units as stored (km, USD) · all data, no date filter · fuel = purchases by `TRIP_ID` · maintenance allocated per km of the truck · trips with no `TRUCK_KEY` excluded and counted · return KPI + totals.

**Logic:** `main.py` route → `kpi_validation.calculate_all()` runs one SQL per KPI (list `KPIS`) through `snowflake_client.fetch_all()` and adds `kpi_id, name, unit`. Decimals are cast to `FLOAT` in SQL so JSON has numbers, not strings.

**Files:** new `backend/app/kpi_validation.py` · `backend/app/main.py` (import + route) · `backend/README.md`.

**Result (2026-10-29, response time ~2 s):**

| Check | Value | Meaning |
|---|---|---|
| KPI 9 Distance Variance | 0.14 % | Trips are on average 0.14% longer than the route's typical km |
| `FCT_TRIPS` → `DIM_ROUTE` | 953,293 / 953,293 matched | Route join is clean |
| KPI 28 Margin Proxy | 3,046.04 USD per trip | Average revenue − fuel − maintenance, over 933,945 trips |
| Trips without `TRUCK_KEY` | 19,348 trips (2.0%) | ⚠️ Model gap: excluded from KPI 28 |
| Fuel purchases with unknown `TRIP_ID` | 4,353 rows, 2,352,817.84 USD | ⚠️ Orphan rows: fuel not linked to any trip |
| Used trips with no fuel purchase | 55,512 trips (5.9%) | To check with the owner: short trips or missing data |
| Fuel used vs all purchases | 1,055,137,876.93 / 1,079,341,007.04 USD | Gap 24,203,130.11 USD = orphans 2,352,817.84 + no-truck trips 21,850,312.27 (reconciles exactly) |
| Maintenance used vs all orders | 208,150,661.15 / 208,150,661.15 USD | Per-km allocation keeps 100% of the cost |

**Tests done:** both queries run in Snowflake ✅ · endpoint returns 200 on a test instance (port 8001) ✅ · margin recomputed by hand: (4,108,119,848.35 − 1,055,137,876.93 − 208,150,661.15) / 933,945 = 3,046.04 ✅ · fuel gap split checked with a separate query ✅. The server on port 8000 runs without `--reload`, so it needs a restart to serve the new route.

### Full model check script ✅ (2026-10-29)
**What I did:** Added [tools/validate_marts.py](tools/validate_marts.py). It runs 53 checks on `DBT_MARTS` and prints one PASS / WARN / FAIL line per check, then a total. Exit code 1 if any FAIL (ready for Airflow later).

**Decisions:** one-off script, not an API route · FAIL = orphan key, duplicate key, or a history ID without exactly one `IS_CURRENT` row · WARN = NULL keys.

**Logic:** three lists (`FOREIGN_KEYS` 33, `UNIQUE_KEYS` 18, `HISTORY_DIMS` 2) + three SQL templates, each returning `ROWS_TOTAL, NULL_KEYS, PROBLEM_KEYS`. It reuses the backend login (`backend/app/infrastructure/snowflake_client.py` since the 2026-10-29 restructure, `backend/.env`), so there is no second copy of the connection code.

**Code:**
```bash
.venv/Scripts/python tools/validate_marts.py
```

**Result (2026-10-29, ~21 s): 53 checks: 40 PASS, 9 WARN, 4 FAIL**

| Status | Check | Count (rows) | Cause found |
|---|---|---|---|
| FAIL | `FCT_DELIVERY_EVENTS.TRIP_ID` not in `FCT_TRIPS` | 5,236 events (2,618 trips) | 1,336 are from the last 10 days (trips not finished yet: `FCT_TRIPS` has only `Completed` trips). The rest go back to 2023-12-29 |
| FAIL | `FCT_DELIVERY_EVENTS.LOAD_ID` not in `FCT_SHIPMENTS` | 4,390 events | The same 4,390 rows have NULL `CUSTOMER_ID`, `ROUTE_ID`, `LOAD_DATE_KEY` (copied from the missing load) |
| FAIL | `FCT_FUEL_PURCHASES.TRIP_ID` not in `FCT_TRIPS` | 4,353 purchases | 3,546 (81%) from the last 10 days → mostly trips not finished yet |
| FAIL | `FCT_SAFETY_INCIDENTS.TRIP_ID` not in `FCT_TRIPS` | 6 incidents | All from 2026-10-25 to 10-28 → trips not finished yet |
| WARN | `FCT_MAINTENANCE.FACILITY_KEY` is NULL | 106,524 of 106,524 (100%) | ⚠️ Column is never filled: a dbt model bug |
| WARN | `FCT_TRIPS` NULL `TRUCK_KEY` / `TRAILER_KEY` / `DRIVER_KEY` | 19,348 / 19,099 / 18,967 (~2%) | Even across 2024–2026. `TRUCK_ID` is also NULL on all of them → missing in the source (dirty rows), not a failed dbt lookup |
| WARN | `FCT_FUEL_PURCHASES` NULL `TRUCK_KEY` / `DRIVER_KEY` | 36,987 / 37,312 (~2%) | Same: `TRUCK_ID` NULL in the source |
| WARN | `FCT_DELIVERY_EVENTS` NULL `CUSTOMER_ID`, `ROUTE_ID`, `LOAD_DATE_KEY` | 4,390 each | Same rows as the `LOAD_ID` FAIL above |
| PASS | All unique keys, all `DIM_*` → `DIM_LOCATION` keys, all `*_DATE_KEY` (except the 4,390), one current row per `CUSTOMER_ID` / `DRIVER_ID` | – | Model structure is sound |

**Tests done:** script ran end to end against Snowflake ✅ · exit code 1 because of the 4 FAILs ✅ · causes checked with extra queries (dates of orphans, NULL `TRUCK_ID` behind NULL `TRUCK_KEY`) ✅.

**Root causes found later (2026-10-29), reported to the owner in [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md):**
- Old orphans are not random: `RAW_DATA.LOADS` has `LOAD00000001`–`LOAD00001950` (`LOAD_DATE` 2023-12-29 to 12-31), but `FCT_SHIPMENTS` starts at 2024-01-01 and `RAW_DATA.TRIPS` starts at `TRIP00001951`. Their child rows (3,900 events, 807 fuel purchases) stay in the facts.
- All 846 events with a load but no trip are recent (unfinished trips).
- `RAW_DATA.MAINTENANCE_RECORDS` has only `FACILITY_LOCATION` (a city), with no facility ID, so `FACILITY_KEY` cannot be found.
- `RAW_DATA.TRIPS` already has an empty `TRUCK_ID` in 34,035 of 1,679,187 rows (2.0%).

### Backend restructure (clean architecture) ✅ (2026-10-29)
**What I did:** Split the flat `backend/app/` (4 files) into layers so the backend can grow to all 8 dashboards and the stream: `api/` → `services/` → `domain/` (contracts) ← `infrastructure/` (Snowflake), plus `core/` and `schemas/`. KPI SQL moved to `.sql` files. Response schemas added. Same URLs, same JSON. Details: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md).

**Decisions:** clean architecture (option C, chosen over layered / feature modules) · repositories have `Protocol` contracts · only KPI SQL in `.sql` files (health/tables SQL stays in the repository) · JSON keys kept exactly as before (upper-case Snowflake columns) · no tests folder for now · URLs not versioned (no `/api/v1`).

**Logic:** route gets its service from `api/dependencies.py` (`Depends`) → service runs the logic on a contract from `domain/repositories.py` → `infrastructure/repositories/snowflake_*.py` runs the SQL (`sql_loader.load_sql()` for `.sql` files) through `snowflake_client.fetch_all()` → route validates the result with its `schemas/` model.

**Files:** moved (`git mv`): `config.py` → `core/config.py` (`.env` path `parents[1]` → `parents[2]`), `snowflake_client.py` → `infrastructure/snowflake_client.py` (import path), `kpi_validation.py` → `services/kpi_validation_service.py` (SQL out, class `KpiValidationService`) · new: `core/errors.py`, `domain/repositories.py`, `infrastructure/sql_loader.py`, `infrastructure/queries/kpis/{distance_variance,margin_proxy}.sql`, `infrastructure/repositories/snowflake_{system,kpi}_repository.py`, `services/system_service.py`, `schemas/{system,kpi_validation}.py`, `api/{dependencies,router}.py`, `api/routes/{health,tables,kpis}.py`, `__init__.py` per folder, `backend/ARCHITECTURE.md` · changed: `main.py` (only builds the app), `backend/README.md` (flow), `tools/validate_marts.py` line 9 (`from app.infrastructure import snowflake_client`). No `.env` change, no new package.

**Tests done:** responses of `/health`, `/api/tables`, `/api/kpis/validation` saved before the change and compared after: byte-for-byte identical (149 / 2,827 / 597 bytes) ✅ · SQL in the `.sql` files equals the old Python strings ✅ · `/docs` lists the same 3 paths plus 4 schemas ✅ · CORS preflight 200 ✅ · no warnings at startup ✅ · service with a fake repository returns both KPI models ✅ · Snowflake error → 503 ✅ · `tools/validate_marts.py` import works ✅. The server on port 8000 still runs the old code until restarted.

### Warehouse KPIs on the dashboard + 30-min refresh ✅ (2026-10-29)
**What I did:** Added `GET /api/kpis/{dashboard_id}?kpi_ids=…`. It calculates every KPI card and chart that the warehouse can answer, for the last 30 days vs the previous 30 days, directly on `DBT_MARTS`. 23 KPIs + 17 charts. KPIs and charts that need the live stream or pipeline metadata return `null`. The dashboard calls it and re-fetches every 30 min. Units switched to metric everywhere (api and mock; the mock was removed on 2026-10-29).

**Decisions:**
- Scope: KPI cards and charts together. No cache (the KPI logic moves to dbt later; now the goal is correct logic).
- One SQL file per KPI (`queries/kpis/`), one per chart (`queries/series/`). The frontend sends the page's KPI ids (`dashboards.js` stays the only list).
- Not in the warehouse → `null` → card shows `-`, chart shows "No data" (no mock fill in api mode). Live map keeps the simulator in api mode (stream is instant, warehouse is refreshed every 30 min).
- Period: 30 days ending 3 days ago (trips land only when completed) vs the 30 days before. Row date = when it happened (`ACTUAL_DATE`, `TRIP_DATE` = dispatch, `PURCHASE_DATE`, `MAINTENANCE_DATE`, `INCIDENT_DATE`, snapshot date).
- Units: metric as in the marts (km, L, L/100km, USD/km, per 1M km).
- KPI rules: 1/2 = `on_time_flag`; 3 = average of late deliveries only (`delay_minutes > 0`: 170.4 min, vs 12.7 min if early deliveries count as 0); 5 = `delay_minutes > 120`; 8 = average per trip, planned = scheduled delivery − scheduled pickup; 20/27/28 fuel cost = consumption-based (`fuel_liters_used` × period price per liter); 21 = `AVERAGE_L_PER_100KM` as the data gives it; 22 = vs national price of the same day from `RAW_DATA.DIESEL_PRICES` (not in the marts); 30 = per fleet truck-day; 43 = per 30 days; 46 = `is_in_maintenance`.
- KPIs 4 and 9 skipped (removed from the dashboards). KPIs 23, 29 stay null (telemetry). Platform page all null (no Airflow/dbt/S3 tables; `SNOWFLAKE.ACCOUNT_USAGE` not authorized for `AIRFLOW_ROLE`).
- `GET /api/kpis/validation` removed (join checks stay in `tools/validate_marts.py`).

**Logic:** dashboard `useKpis` → `apiSource.getKpis(id)` → `GET /api/kpis/{id}?kpi_ids=…` → route checks the id → `KpiService.dashboard()` builds the period dates → for each KPI id in `KPI_QUERIES` runs `kpis/<name>.sql` (2 rows: `value`, `previous`), for each chart in `DASHBOARD_SERIES` runs `series/<name>.sql` (or null) → `SnowflakeKpiRepository.fetch_rows()` lower-cases keys and turns `Decimal` into `float` → `DashboardResponse`. Full flow: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md), formulas: [backend/README.md](backend/README.md).

**Result (period 2026-09-27 to 2026-10-26 vs 2026-08-28 to 2026-09-26):**

| KPI | Current | Previous | Meaning |
|---|---|---|---|
| 1 On-Time Delivery (%) | 93.27 | 93.39 | 93 of 100 deliveries start within the 15-min grace period |
| 2 On-Time Pickup (%) | 65.97 | 65.92 | Pickups are late far more often than deliveries |
| 3 Avg Delivery Delay (min) | 170.4 | 174.4 | A late delivery is ~2.8 h late on average |
| 5 Severe Delay (%) | 3.39 | 3.40 | 3.4% of deliveries are more than 2 h late |
| 6 Destination Queue (min) | 31.9 | 31.2 | ~32 min wait before unloading |
| 7 Dock Time (min) | 89.1 | 88.8 | ~1.5 h loading / unloading per stop |
| 8 Trip Duration Variance (%) | −15.6 | −15.7 | Trips take 16% less than planned (schedule slack) |
| 19 Total Fuel Spend (USD) | 29,023,609 | 29,688,871 | Fuel bought in 30 days |
| 20 Fuel Cost per km (USD/km) | 0.345 | 0.353 | |
| 21 Fuel Efficiency (L/100km) | 36.27 | 36.24 | = 6.5 mpg, inside the expected 5.8–7.8 mpg |
| 22 Fuel Price Variance (%) | 2.70 | 2.57 | Paid 2.7% above the national price (state offsets included) |
| 24 Idle Time Share (%) | 9.14 | 9.03 | |
| 26 Revenue per km (USD/km) | 1.451 | 1.452 | |
| 27 Fuel Cost % of Revenue (%) | 23.79 | 24.30 | = KPI 20 / KPI 26 (checked) |
| 28 Margin Proxy per Trip (USD) | 3,094.53 | 3,117.40 | Revenue − fuel − maintenance, not profit |
| 30 Km per Truck per Day (km) | 538.1 | 561.3 | ⚠️ incomplete last days, fixed in the "Follow-up" below |
| 36 Incident Rate (per 1M km) | 0.756 | 0.689 | = ~1.2 per 1M mi, near the expected 1.4 |
| 38 Claim Cost (USD) | 423,420 | 564,630 | |
| 41 Total Maintenance Cost (USD) | 6,175,651 | 6,157,836 | |
| 42 Maintenance Downtime (h) | 77,203 | 78,285 | |
| 43 Orders per Truck (orders) | 0.629 | 0.629 | = ~7.7 per year, expected ~8 |
| 44 Maintenance Cost per km (USD/km) | 0.077 | 0.073 | |
| 46 Truck Availability (%) | 97.90 | 97.91 | |

**Files:**
- Backend new: `services/kpi_service.py`, `schemas/dashboard.py`, `queries/kpis/` 22 new files + `margin_proxy.sql` rewritten (per period, consumption fuel), `queries/series/` 17 files.
- Backend changed: `domain/repositories.py` (`fetch_kpi` → `fetch_rows(query, params)`), `infrastructure/repositories/snowflake_kpi_repository.py`, `api/routes/kpis.py`, `api/dependencies.py`, `README.md`, `ARCHITECTURE.md`.
- Backend deleted: `services/kpi_validation_service.py`, `schemas/kpi_validation.py`, `queries/kpis/distance_variance.sql`.
- Dashboard new: `components/NoData.jsx`.
- Dashboard changed: `data/api/apiSource.js` (sends `kpi_ids`, simulator for the stream), `hooks/useKpis.js` (30-min refresh), `kpis/definitions.js` (metric units, formulas), `components/charts.jsx` + `DataTable.jsx` (No data, tooltip rounding), `pages/{Executive,Delivery,Fuel,Safety,Maintenance,ColdChain}Page.jsx`, `data/mock/{kpiValues,dashboards}.js` (metric), `data/contract.js`, `README.md`.
- No `.env` change, no new package, no database change (read-only).

**Tests done:** all 23 KPI SQL and 17 chart SQL run on Snowflake (4.5 s and 9.5 s for all) ✅ · endpoint on a test instance (port 8001) for all 8 dashboards, 1–4 s each ✅ · unknown id → 404 ✅ · JSON numbers are floats, dates `YYYY-MM-DD` ✅ · KPI 27 = KPI 20 / KPI 26 ✅ · found and fixed a Snowflake precision bug (KPI 36 gave exactly 1.0: a division keeps 6 decimals, so multiply by 1,000,000 first) ✅ · `npm run build` passes ✅. Not done: clicking through the pages in a browser in api mode.

**Follow-up (2026-10-29): trips by finish day, window ends yesterday, reconnect on expired login, backend restarted**
- **Problem:** trips counted on their start day (`TRIP_DATE`). A trip lands only when completed (59 h on average, up to 5 days), so the last start days were incomplete (24 Oct 934 trips, 25 Oct 692, 26 Oct 371) and trip totals were ~3–4% low.
- **Fix:** trips count on the day they finished (`ARRIVAL_TS::DATE`). By finish day every day is complete (22–28 Oct: 857–951 trips). 15 SQL files changed (`trip_date` → `arrival_ts::DATE`): KPIs 8, 20, 21, 24, 26, 27, 28, 30, 36, 44 and charts `unit_economics_trend`, `fuel_efficiency_by_route`, `fuel_efficiency_by_truck`, `driver_scorecard`, `cost_by_model_year`. Window now ends yesterday (`DATA_LAG_DAYS = 1`).
- **Result:** KPI 30 = 559.79 vs 559.77 km (the fake drop 538 vs 561 is gone). Period now 2026-09-29 to 2026-10-28.
- **Connection fix:** `snowflake_client.fetch_all()` catches an expired login (`ReauthenticationRequest`, or codes 390111 / 390112 / 390114), opens a new connection and retries once. Tests: simulated expiry → 2 attempts, new session ✅ · real end of our session (`SYSTEM$ABORT_SESSION`, gave 390111) → next query works on a new session ✅ · a normal SQL error (2003, unknown table) is still raised, no retry ✅.
- **Backend restarted** on port 8000 with `--reload`, as a separate Windows process (survives the terminal). Logs: `backend/uvicorn.log`, `backend/uvicorn.err.log` (added to `.gitignore`), PID in `backend/uvicorn.pid`. `/health` 200, all dashboards 200 in 0.2–1.6 s ✅.
- **Files:** `backend/app/infrastructure/snowflake_client.py`, `backend/app/services/kpi_service.py`, the 15 SQL files above, `backend/README.md`, `backend/ARCHITECTURE.md`, `.gitignore`.

### Live stream from Kafka over SSE ✅ (2026-10-29)
**What I did:** The backend reads the two Kafka silver topics, keeps the latest row of every truck in memory, makes alerts from the row flags, calculates the live KPIs, and pushes all of it to the dashboard over Server-Sent Events (`GET /api/stream`). The live map in api mode now uses this instead of the simulator, and shows a new "Live KPIs" panel. Details: [backend/README.md](backend/README.md#live-stream-get-apistream), [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md#live-stream-files-get-apistream).

**What the data is (measured 2026-10-29, read-only):**
| Topic | Partitions | Batch every | Rows per batch | Age of newest reading on arrival | Duplicates |
|---|---|---|---|---|---|
| `fleet.silver.telemetry.v1` | 3 | 5.0 min | ~2,150 (one per truck) | ~10 min | ~0.4% (same row again, without `updated_at`) |
| `fleet.silver.reefer.v1` | 3 | 5.0 min | ~1,180 (one per truck) | ~10 min | same |
- Proof that it is batches, not a continuous stream: Kafka's own timestamps put 9,000 telemetry messages of 20 min into only 6 seconds; a 400 s live watch saw messages in 2 seconds only.
- Kafka keeps ~11 h (oldest message 2026-10-28 23:24 UTC). The last hour = ~26k telemetry + ~14k reefer messages.
- `is_idling` = `motion_status = IDLING` (idle now, not "over 30 min"). `stream_latency_sec` is always null. No `ingest_ts` in silver rows.
- First connection was blocked (timeout from my PC, Colab and this machine); the owner opened port 9092, then it worked.

**Decisions:**
- aiokafka (async, same loop as FastAPI) · no consumer group, nothing committed · state in a Python dict in memory (no Redis) · FastAPI's built-in SSE (`fastapi.sse`, no new SSE package).
- `STREAM_HISTORY_MINUTES=60`, one key for both: read back 60 min from Kafka on start, drop rows whose `event_ts` is older than 60 min.
- Duplicates / late rows: keep a row only if its `event_ts` is newer than the truck's stored row.
- Send every 1 s, only when something changed. Every time rule uses `event_ts`, so a faster upstream batch (1 min, 2 s) needs no code change.
- Live KPIs: truck counts (+ per `motion_status`), counts of `is_speeding` / `is_engine_overheating` / `is_low_fuel` / `is_reefer_unit_failure`, cold-chain compliance (%) overall and per `commodity_type`, data age (min).
- Alerts option b: flag alerts (`SPEEDING`, `ENGINE_OVERHEATING`, `LOW_FUEL`, `COLD_CHAIN_BREACH`, `REEFER_UNIT_FAILURE`) + `EXCESSIVE_IDLING` after 30 min of `is_idling`. `IDLING` alone is only a map color. No `ROUTE_DEVIATION` live (no flag).
- New viewer gets a full snapshot: every truck's latest rows, active alerts, last 40 alert changes, KPIs.
- Endpoint `/api/stream` (the dashboard `.env` had `/stream`, changed).

**Logic:** `KafkaStreamSource.messages(since)` (one consumer on both topics, each partition moved to `since` with `offsets_for_times`) → `StreamService._read()` calls `FleetState.apply(kind, row, now)` for each message (retries every 10 s if Kafka fails) → every second `StreamService._send_changes()` calls `FleetState.take_changes(now)` (drops rows older than 60 min, ends their alerts, returns the new rows + alert changes + KPIs, or nothing) and puts the events in every viewer's queue → `GET /api/stream` yields the snapshot, then the queue, as SSE events `telemetry`, `reefer`, `alert`, `kpis` → dashboard `apiSource.subscribe()` (one shared `EventSource`) → `useFleetState()` → map, alert feed, Live KPIs panel.

**Files:**
- Backend new: `app/domain/stream_source.py`, `app/infrastructure/kafka_stream_source.py`, `app/services/fleet_state.py`, `app/services/stream_service.py`, `app/schemas/stream.py`, `app/api/routes/stream.py`.
- Backend changed: `app/core/config.py` (4 settings), `app/api/dependencies.py` (one shared `stream_service`), `app/api/router.py`, `app/main.py` (start/stop the stream), `requirements.txt` (`aiokafka>=0.12`, `fastapi>=0.141`), `.env.example`, `README.md`, `ARCHITECTURE.md`.
- Dashboard changed: `src/data/api/apiSource.js` (EventSource again instead of the simulator), `src/hooks/useFleetState.js` (`kpis` event, status from `motion_status`, new alert types), `src/pages/LiveMapPage.jsx` (Live KPIs panel, new columns), `src/kpis/definitions.js` (`SPEEDING`, `ENGINE_OVERHEATING`, `LOW_FUEL`), `src/data/mock/fleetSimulator.js` (silver columns + `kpis` event), `src/data/contract.js`, `.env.example`, `README.md`.
- **`.env` changes:** `backend/.env` + 4 lines (`KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TELEMETRY_TOPIC`, `KAFKA_REEFER_TOPIC`, `STREAM_HISTORY_MINUTES`); `dashboard/.env.local` `VITE_STREAM_URL` → `http://localhost:8000/api/stream`.
- Package installed in `.venv`: `aiokafka 0.15.0`. No database change.

**Tests done:**
- Logic with fake rows (7 checks, all pass ✅): duplicate / late / older-than-60-min rows dropped · flag alert starts and ends with the same `anomaly_id` · `EXCESSIVE_IDLING` not at 29 min, yes at 30 min with `start_ts` = first idle row · KPIs incl. compliance without null `cargo_temp_f` and per commodity · snapshot = one event per alert (latest version) · rows expire after 60 min and their alerts end · `StreamService`: snapshot first, then changes, viewer queue removed on disconnect.
- Real Kafka on a test instance (port 8001) ✅: snapshot 4.1 MB (telemetry 3.29 MB = 5,000 rows × 658 B, reefer 0.76 MB), first byte 0.66 s; KPIs: 5,000 trucks (3,543 parked / 1,215 driving / 242 idling), 46 speeding, 55 low fuel, 0 overheating, 1,205 reefers, compliance 100.0%, data age 13.0 min; 234 active alerts (133 `EXCESSIVE_IDLING`, 55 `LOW_FUEL`, 46 `SPEEDING`).
- Kafka down (first version had a bug: topic "not found") → the reader logged it and retried every 10 s, the API kept answering ✅. Bug fixed (topics passed to the consumer, aiokafka assigns all 6 partitions).
- `npm run build` passes ✅. Not done: clicking through the live map in a browser.

### Mock data removed ✅ (2026-10-29)
**What I did:** Deleted the dashboard's mock data source (fake KPI numbers, fake chart series, in-browser 5,000-truck simulator) and the `VITE_DATA_SOURCE` switch. The dashboard now always reads the backend: warehouse KPIs over REST, live stream over SSE.

**Decisions:**
- Remove the switch, not keep it with one option: one source means no dead code path.
- `data/index.js` stays as the only data import of the components, so no hook or page changed.
- `ROUTE_DEVIATION` kept (color, label, status priority) for a future stream flag; only its comments changed (the backend never sends it today).
- The dashboard is not deployed, so nothing public breaks.

**Logic:** pages → hooks (`useKpis`, `useStream`) → `data/index.js` (`export { apiSource as dataSource }`) → `apiSource` → backend `GET /api/kpis/{id}` and `GET /api/stream`. KPIs/charts not in the warehouse show `-` / "No data" (same as before in api mode).

**Files:**
- Deleted: `dashboard/src/data/mock/` (6 files: `mockSource.js`, `dashboards.js`, `fleetSimulator.js`, `kpiValues.js`, `reference.js`, `rng.js`, 746 lines).
- Changed: `dashboard/src/data/index.js`, `src/config.js` (no `dataSource`), `src/components/Layout.jsx` (commented-out data badge + unused `config` import removed), `src/data/contract.js`, `src/kpis/definitions.js`, `src/pages/ColdChainPage.jsx` (comments), `dashboard/.env.example`, docs (`dashboard/README.md` section 9 removed and sections renumbered, `RUN.md`, `README.md`, `backend/ARCHITECTURE.md`, this log, `worklog_dashboard.md`).
- **`.env` changes:** `dashboard/.env.example`: `VITE_DATA_SOURCE` removed. `dashboard/.env.local` not touched: its `VITE_DATA_SOURCE=api` line is now unused (safe to delete).

**Tests done:** `npm run build` passes ✅ · no `mock` / `VITE_DATA_SOURCE` reference left in `dashboard/src` ✅. Not done: clicking through the pages in a browser.

### Stream KPIs + moving trucks from Kafka ⏳ (steps 1 and 2 of 3 ✅, 2026-10-29)
Plan and decisions: [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md). Step 1 = backend KPIs + charts ✅ · step 2 = pages show them ✅ (see "Dashboard pages show the stream KPIs" below) · step 3 = trucks replay by `event_ts` ⬜.

**What I did (step 1):** Every KPI and chart that needs telemetry / reefer data is now calculated **from Kafka** (not the warehouse, which has no stream table, so they were `null`). The backend keeps every Kafka row (only the columns the KPIs read), calculates KPIs 10, 11, 12, 13, 14, 15, 16, 23, 29, 33, 34 and the charts `trip_temperature`, `excursions_by_trailer`, `excursion_rate_by_ambient`, `high_risk_trips`, `time_in_state` once per Kafka batch, and sends them in a new SSE event `stream_kpis` on `GET /api/stream`. New filter `?events=stream_kpis` so pages without the map get ~1 KB instead of ~4 MB.

**Decisions:** window = last 60 min of `event_ts` (ending at the newest row) vs the 60 min before · no `trip_id` / `load_id` in Kafka → one trailer / truck in the window = one trip (assumption, KPIs 11, 15, 16) · KPI 29 = `DRIVING` time / all time · a row counts until the next row of its truck/trailer, max 15 min · only the needed columns kept (full rows = 223 MB for 120 min) · same shapes as `GET /api/kpis`, so the pages can use them as they are · KPIs 35, 51–53 stay `null` (not in Kafka).

**Found while testing on real data (and fixed):** KPI 34 was 49 now vs 153 before (edge effects): (1) an idle run is now counted when it **reaches** 30 min (same moment as the alert), not when it starts; (2) a run that begins with the first kept row is skipped (its real start is unknown); (3) 30 extra minutes are kept before the previous window so its runs have a known start. After: 71 vs 64.

**Logic:** `FleetState.apply()` → `StreamHistory.add()` (dedup `vehicle_id` + `event_ts`, `COLUMNS` only, drops rows older than `kept()` = 2 × 60 + 30 min before the newest) → `take_changes()` / `snapshot()` call `stream_kpis()` (calculates again only when rows were added, and is sent to every viewer even if a new viewer's snapshot calculated it first) → `stream_kpis.calculate()`: `_tracks` (rows per truck/trailer, sorted, minutes per row) → `_runs` (flag runs) → `_excursions` (≥ 2 `is_temp_breach` rows) → `_window_kpis()` for the window and the previous one + `_series()` → `StreamKpis` → SSE `stream_kpis`. `StreamService._read()` reads back `kept()` from Kafka on start.

**Files:**
- Backend new: `app/services/stream_history.py`, `app/services/stream_kpis.py`.
- Backend changed: `app/services/fleet_state.py` (history, `stream_kpis()`, `EXCESSIVE_IDLING_AFTER` moved to `stream_kpis.py`), `app/services/stream_service.py` (read back `kept()`), `app/schemas/stream.py` (`StreamKpis`, `EventName`), `app/api/routes/stream.py` (`?events=`), `app/services/kpi_service.py` (docstring), `.env.example` (comment), `README.md`, `ARCHITECTURE.md`.
- Dashboard changed: `src/data/contract.js` (docs only: `stream_kpis`, `StreamKpis`, `?events=`).
- **`.env` changes:** none (`backend/.env.example` comment only). No database change.

**Tests done:**
- Fake rows, values worked out by hand: **36 checks, all pass ✅** (minutes per row + 15-min cap · excursions: 1 row = none, null temp inside a run · KPIs 10–16, 23, 29, 33, 34 + previous window · window edges · all 5 charts · empty data → null · run at the first kept row skipped · history dedup / too old / expiry / columns · `stream_kpis` in snapshot and changes, still sent after a snapshot, not sent for a duplicate). Script: scratchpad `test_stream_kpis.py` (not in the repo).
- Real Kafka (2026-10-29 ~13:10 UTC, window to 13:00 UTC): 100,267 messages read, 99,827 rows kept = **42 MB**, `calculate()` **0.65–0.85 s**, event **0.9 KB**. Values (now vs previous): KPI 10 99.9 / 100.0 % · 11 100.0 / 99.9 % · 12 0 / 1 · 13 – / 85.0 min · 14 – / 6.2 °F · 15 0.1 / 0.1 % · 16 3.0 / 2.5 min per trailer · 23 1,209.7 / 1,232.8 L · 29 34.6 / 34.1 % · 33 0.08 / 0.08 per 100 km · 34 71 / 64.
- Running backend (port 8000, after reload) ✅: `?events=stream_kpis` → only `stream_kpis` (989 bytes); no filter → all 5 events (3.9 MB snapshot); `?events=nope` → 422.

### KPIs without a data source removed ✅ (2026-10-29)
**What I did:** With the mock gone, every KPI card, chart and chart column that neither the warehouse (`DBT_MARTS`) nor Kafka can fill was removed from the dashboard, with its definition (also gone from the KPI Guide).

| Removed | Page | Why no source |
|---|---|---|
| KPI 35 Route Deviation Rate | Safety | needs each trip's origin–destination line; Kafka has no `trip_id` / route |
| KPIs 51 Detection Precision, 52 Detection Recall, 53 Time-to-Detect | Live | need `gen_anomaly_labels` (only in S3, not connected) |
| KPIs 55 End-to-End Latency, 56 Data Completeness, 59 S3 vs Snowflake Gap, 61 Pipeline Success Rate, 62 dbt Test Pass Rate, 63 API Success Rate, 64 Warehouse Cost | Platform | no `ingest_ts` / stream in Snowflake, no "expected rows", no S3 access, Airflow not built, dbt results not stored, the APIs are the generator's, no `ACCOUNT_USAGE` access |
| Charts `pipeline_runs`, `credits_trend`, `row_counts` | Platform | same reasons (Airflow, `ACCOUNT_USAGE`, S3) |
| Column `kpi_11` (weekly) in `service_trend` | Executive | Kafka keeps ~13 h, not weeks |
| Columns `kpi_33`, `kpi_34` (per driver) in `driver_scorecard` | Safety | Kafka has no `driver_id` |

**Decisions:** KPIs 54, 57, 58, 60 have a source (Kafka / backend) → kept, to be built now · the live page has no KPI cards any more, so it does not call `GET /api/kpis/live` (stream only) and `live` was removed from the backend (`/api/kpis/live` → 404) · removed KPIs are also deleted from `definitions.js` (and so from the KPI Guide) · `QUESTIONS['Outcome 6']` and the KPI group "G. Anomaly Detection Quality" were only used by 51–53 → removed.

**Files:**
- Dashboard: `src/dashboards.js` (live `[]`, safety without 35, platform `[54, 57, 58, 60]`), `src/kpis/definitions.js` (11 KPIs, Outcome 6, group G removed → 39 KPIs), `src/hooks/useKpis.js` (no call when a page has no `kpiIds`), `src/pages/PlatformPage.jsx` (cards only), `src/pages/ExecutivePage.jsx` (`kpi_11` line), `src/pages/SafetyPage.jsx` (`kpi_33`/`kpi_34` columns), `src/data/contract.js`, `README.md`.
- Backend: `app/services/kpi_service.py` (`live` removed, `platform` no series, `SERIES_NOT_IN_WAREHOUSE` without the pipeline series), `queries/series/driver_scorecard.sql` (`NULL AS kpi_33/kpi_34` removed), `queries/series/service_trend.sql` (comment), `README.md`, [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md).
- **`.env` changes:** none. No database change.

**Tests done:** `npm run build` passes ✅ · every page's `kpiIds` exists in `KPIS` ✅ · no reference left to the removed KPIs / series / columns in `dashboard/src` ✅ · backend: `/api/kpis/live` → 404 ✅, `/api/kpis/platform` → 200 with `series: {}` ✅, `driver_scorecard` columns = `driver_id, first_name, last_name, distance_km, kpi_24, incidents` ✅, `service_trend` = `week_start, kpi_1` ✅.

### Platform KPIs 54, 57, 58, 60 (stream) + 65 (warehouse) ✅ backend (2026-10-29)
**What I did:** Built the 4 platform KPIs that have a source, and a new KPI 65.
| KPI | Source | Rule | Unit |
|---|---|---|---|
| 54 Ingestion Throughput | Kafka messages | messages received / 3,600 s, last 60 min of Kafka time vs the 60 before | events/s |
| 57 Duplicate Rate | Kafka messages | rows with the same `vehicle_id` + `event_ts` as a kept row / received | % |
| 58 Rejection Rate | Kafka messages | not JSON, or no valid `vehicle_id` / `event_ts` / received | % |
| 60 Data Freshness | Kafka messages | now − Kafka time of the newest message (no previous) | min |
| 65 Warehouse Data Freshness (new, not in the catalog) | Snowflake `RAW_DATA` | now − newest `_AIRBYTE_EXTRACTED_AT` over the 13 tables (no previous) | min |

**Decisions:** the Kafka reader passes each message's partition + offset + Kafka time (`StreamMessage`), so (1) a message read again after a Kafka failure is skipped, never counted as a duplicate, and (2) a broken message (no `event_ts`) can still be placed in a window by its Kafka time · freshness on 2 cards: 60 = stream, 65 = warehouse (id and names chosen by the owner) · `stream_kpis` is also sent every minute, so KPI 60 grows between batches · one `pct()` helper shared by `stream_kpis.py` and `platform_stats.py`.

**Logic:** `KafkaStreamSource` → `StreamMessage(kind, row | None, partition, offset, timestamp)` → `StreamService._read()` → `FleetState.apply(message)`: `PlatformStats.is_new()` (skip a re-read) → `StreamHistory.add()` returns `added` / `duplicate` / `old` → `PlatformStats.count(duplicate, rejected)` per minute of Kafka time → `stream_kpis(now)` = row KPIs (cached, recalculated per batch) + `PlatformStats.kpis(now)` → SSE `stream_kpis`. A rejected message raises after being counted; `StreamService` logs it. KPI 65: `KPI_QUERIES[65]` → `queries/kpis/warehouse_data_freshness.sql` → `GET /api/kpis/platform`.

**Files:**
- Backend new: `app/services/platform_stats.py`, `app/infrastructure/queries/kpis/warehouse_data_freshness.sql`.
- Backend changed: `app/domain/stream_source.py` (`StreamMessage`), `app/infrastructure/kafka_stream_source.py` (yields `StreamMessage`, no own warning), `app/services/fleet_state.py` (`apply(message)`, `PlatformStats`, send rule, `STREAM_KPIS_EVERY`), `app/services/stream_history.py` (`add()` result), `app/services/stream_kpis.py` (`pct()` shared), `app/services/stream_service.py` (messages, one warning per rejected message), `app/services/kpi_service.py` (`65`), `README.md`, `ARCHITECTURE.md`.
- Dashboard: `src/kpis/definitions.js` (meanings of 54, 57, 58, 60; new 65; group to 65 → 40 KPIs), `src/dashboards.js` (platform `[54, 57, 58, 60, 65]`), `src/data/contract.js`, `README.md`.
- Package installed in `.venv`: `tzdata 2026.6` (already in `requirements.txt`, added by the Cairo-time change; without it `ZoneInfo("Africa/Cairo")` fails on Windows and the backend does not start).
- **`.env` changes:** none. No database change.

**Tests done:**
- Fake messages, values by hand: **51 checks, all pass ✅** (the 36 before, plus: re-read skipped · lower offset with newer Kafka time = new · duplicate → only `stream_kpis` · not JSON / no `vehicle_id` raise and are counted · refresh after 1 min, not after 30 s · KPI 54 = 10 / 60 s, 57 = 1 of 10, 58 = 2 of 10 and 1 of 4, 60 = 2 min).
- Running backend (2026-10-29 13:45 UTC): 54 = **11.17** events/s (prev 11.12) · 57 = **0.4 %** (prev 0.43) · 58 = **0.0 %** · 60 = **0.1 min** · 65 (REST) = **52.6 min** · `npm run build` ✅.

### Live page: changed values light up for 2 s ✅ (2026-10-29)
**What I did:** On the Live Fleet Map, a value that changes because of new stream data lights up (sky-blue border + background) for 2 s: a **Live KPI tile** when its number changes, an **alert feed row** when the alert is new or ends. Scope chosen by the owner: live page only, each changed value (no header badge).

**Logic:** `hooks/useHighlight.js` `useHighlight(value, lightFirst)` keeps the previous value in a ref; when the value changes it sets `lit` = true, and a second effect turns it off after `HIGHLIGHT_MS` (2,000 ms); a new change while lit restarts the 2 s. The first value does not light (page load) unless `lightFirst`. `LiveKpiTile` uses it with the tile's value; `AlertFeedRow` uses it with `end_ts` and `lightFirst` = the alert arrived after the snapshot. `useFleetState` marks those alerts **when the message arrives** (`snapshotDone` becomes true at the first `kpis` event, the last event of the snapshot; `newAlertIds` keeps the last 40 ids after it).

**Bug found in the browser test (and fixed):** the first version used `liveKpis !== null` to know the snapshot was over, and all 40 alert rows lit on page load: React draws the whole snapshot at once, after the `kpis` event was already handled. Marking alerts at message time does not depend on when React draws.

**Files:** new `dashboard/src/hooks/useHighlight.js`; changed `src/hooks/useFleetState.js` (`snapshotDone`, `newAlertIds`), `src/pages/LiveMapPage.jsx` (`LiveKpiTile`, `AlertFeedRow`, `LIT` classes), `dashboard/README.md`. **`.env` changes:** none. No database change.

**Tests done:** `npm run build` ✅ · headless Edge on the real stream (3 runs, 2026-10-29 14:09–14:15 UTC), lit elements sampled every 0.5 s: page load and reload → 0 lit ✅ (first version: 40 rows, the bug) · reefer rows expiring → "Reefers reporting" + "Data age" lit ✅ · Kafka batch 14:14:55 → 4 then 5 tiles and 2 then 30 new alert rows lit ✅ · every lit period lasted **2.1 s** ✅.

### Dashboard pages show the stream KPIs (step 2) ✅ (2026-10-29)
**What I did:** Every dashboard page now listens to the `stream_kpis` SSE event and shows its values in the KPI cards and charts that the warehouse returns as `null`: KPIs 10–16, 23, 29, 33, 34 (Kafka rows), 54, 57, 58, 60 (Kafka messages) and the 5 stream charts. Pages without the map ask the backend only for `stream_kpis` (`?events=`), ~3 KB instead of ~4 MB.

**Decisions (owner):**
- Merge in `DashboardShell` (one place, pages unchanged, no list of stream KPI ids in the frontend): a KPI id or series key the stream sends replaces the warehouse one.
- `apiSource` opens the shared `EventSource` with `?events=` of the subscribed event types and reconnects when they change.
- The header shows a 2nd period line "Live (Kafka): 60 min to 18:15 vs previous 60 min", only on pages with a stream card or chart (not a tag per card).
- No new `useStreamKpis` hook (plan): `useStream('stream_kpis', setStream)` is one line.

**Logic:** `DashboardShell` → `useKpis(id)` (REST, 30 min) + `useStream('stream_kpis', setStream)` → `mergeStream(data, stream)`: stream KPIs replace the REST row with the same `kpi_id`, `{ ...data.series, ...stream.series }` → `KpiGrid` + `children(series)`. Before the first `stream_kpis`, the REST data is shown as it is. `apiSource.subscribe()` adds `{ eventType, listener }` to `subscriptions` and calls `scheduleReconnect()`: one microtask later (after the whole React commit) it closes the old `EventSource` and opens `VITE_STREAM_URL?events=<subscribed types>`, so a page change = one new connection with its own snapshot. `unsubscribe` removes the listener at once. `pagehide` closes the connection, `pageshow` from the back/forward cache reconnects.

**Bug found in the browser test (and fixed):** after ~3–5 full page loads (reload / typed URL) every request to the backend hung, even `/health`. Cause: the browser keeps left pages in its back/forward cache with their SSE connection open, and allows only 6 connections per host (`netstat`: the test Edge held exactly 6 to `:8000`; with `--disable-features=BackForwardCache` the problem was gone). Before this step only the live map had a connection; now every page has one, so it showed up. Fix: close on `pagehide`. Also fixed before the test: the header check read `stream.series` while `stream` was still `null` (crash before the first event); the Cold Chain chart title showed "null" (Kafka has no `trip_id`) → now `trailer_id (vehicle_id, commodity)`.

**Files:** `dashboard/src/components/DashboardShell.jsx` (merge, `useStream`, 2nd period line), `src/data/api/apiSource.js` (`subscriptions`, `scheduleReconnect`, `?events=`, `pagehide`/`pageshow`), `src/pages/ColdChainPage.jsx` (title, comment), `src/hooks/useStream.js` (comment), `dashboard/README.md` (sections 2, 3, 6, 7, 8, 13), `STREAM_KPIS_PLAN.md` (step 2 rows), this log. **`.env` changes:** none. No database change. No backend change.

**Tests done:**
- `npm run build` ✅.
- `apiSource.js` bundled with Vite and run in Node against the running backend: **9 checks pass ✅** (1 subscriber → 1 connection `?events=stream_kpis` · snapshot received · page change with 5 subscribers → exactly 1 new connection, old one closed, URL has the 5 events · map snapshot received · old handler not called again · all unsubscribed → closed).
- `mergeStream` with real REST + stream data, 6 pages ✅: every card filled (e.g. cold chain 11 = 99.7 %, 12 = 3, 13 = 11.7 min; platform 54 = 11.16 events/s, 60 = 1.5 min), no series left `null`, no duplicate `kpi_id`, live period line on cold chain / executive / safety / fuel / platform and not on delivery.
- Headless Edge on the dev server (2026-10-29 ~18:10–18:20 Cairo): 11 sidebar page changes incl. the live map → all cards filled, live line where expected, backend always answering, 0 connections left ✅ · 9 full page loads after the `pagehide` fix → all fine ✅ (before the fix: stuck from the 4th) · Back button → page back with data ✅ (in headless Edge the page reloaded instead of coming from the cache, so the `pageshow` reconnect branch was not exercised).

**Still open:**
- KPI 60 (and 65) have no previous value → the card says "no change vs previous" (misleading for a "now" value).
- High-risk trips table keeps a `trip_id` column that is always `-` (Kafka has no `trip_id`).
- The live page also gets `stream_kpis` (DashboardShell subscribes on every page), ~3 KB per batch, not shown there.

### Live map: facilities, clickable legend, parked split ✅ (2026-10-29)
**What I did:** The live map now shows the **50 facilities** as small buildings, its area comes from the warehouse locations, `PARKED` trucks are split into "at facility" and "resting on route", and the legend is clickable (hide / show trucks by status). The Delivery page lane map got the same clickable filters (on-time band, origin city). Trucks are drawn bigger. Details: [dashboard/README.md](dashboard/README.md).

**Logic:**
- **Facilities + map area:** [tools/export_map_data.py](tools/export_map_data.py) reads `DIM_FACILITY` + `DIM_LOCATION` once and writes `dashboard/src/data/facilities.js` (`FACILITIES`, `MAP_BOUNDS` = min/max lat/lon of all locations and facilities). No backend call; run the script again only when facilities change. `projection.js` centers the map on `MAP_BOUNDS` + 1° padding (before: fixed center 38°N, 96°W). `FacilityLayer.jsx` draws each facility as 2 boxes (hall + office); hover shows name, type, city, state.
- **Parked split:** `statusOf()` in `useFleetState.js`: a `PARKED` truck within **10 mi** of the nearest facility = `PARKED_AT_FACILITY` (loading / waiting), farther = `RESTING_ON_ROUTE` (the driver's 10-hour rest). The distance is cached per row, so re-renders do not repeat the 50-facility search.
- **Clickable legend:** `FilterChips.jsx` = one chip per item (color, label, count) + Show all / Hide all, returns a new `Set` of hidden keys. Live map: `TruckLayer` skips trucks whose status is hidden (the selected truck is always drawn). Delivery: a lane is drawn only if its on-time band **and** its `origin_city` are shown ("Showing N of M lanes").
- **Truck size:** `TRUCK_LENGTH` 0.25 → 1 scene unit, `HEIGHT` 0.1 → 0.4, so the model reads when zoomed in.
- `MARKER_COLOR` moved to `MapCanvas.jsx` and is shared by the Delivery cities and the facility halls (was `CITY_COLOR` in `RouteArcs.jsx`).

**Files:**
- New: `tools/export_map_data.py`, `dashboard/src/data/facilities.js` (generated), `src/scene/FacilityLayer.jsx`, `src/components/FilterChips.jsx`.
- Changed: `src/hooks/useFleetState.js` (`MOTION_STATUS_LABEL`, `PARKED_AT_FACILITY` / `RESTING_ON_ROUTE`), `src/pages/LiveMapPage.jsx` (facilities, hover box, legend chips under the map), `src/pages/DeliveryPage.jsx` (lane filters, `LaneHoverBox`), `src/scene/TruckLayer.jsx` (`hiddenStatuses`, size), `src/scene/projection.js` (`MAP_AREA`), `src/scene/MapCanvas.jsx` (`MARKER_COLOR`), `src/scene/RouteArcs.jsx`, `dashboard/README.md`.
- **`.env` changes:** none. No database change (read-only). No backend change.

**Tests done:** `npm run build` passes ✅.
