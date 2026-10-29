# Fleet Dashboard API (backend)

FastAPI in front of Snowflake (warehouse KPIs) and Kafka (live stream over SSE). The React dashboard ([../dashboard](../dashboard)) calls it at `http://localhost:8000/api`.
Login is username + password, read from `backend/.env`. No Snowflake or Kafka value is written in code.

## Run
```bash
# from the project root, once: install into the shared .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt

# config: copy and fill with the values from the Snowflake owner
cp backend/.env.example backend/.env

# start (from backend/)
cd backend
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3
```
`--timeout-graceful-shutdown 3`: an open SSE connection (a dashboard tab on the live map) never ends by itself, and uvicorn waits for every
connection before it stops or reloads. With this flag it closes them after 3 s; the browser reconnects and gets a fresh snapshot.
Open http://localhost:8000/docs to try the endpoints.

## Config (`backend/.env`, git-ignored)
| Variable | Required | Meaning |
|---|---|---|
| `SNOWFLAKE_API_ACCOUNT` | yes | Account identifier `ORGNAME-ACCOUNTNAME` |
| `SNOWFLAKE_API_USER` / `SNOWFLAKE_API_PASSWORD` | yes | Login |
| `SNOWFLAKE_API_DATABASE` | yes | Database to query |
| `SNOWFLAKE_API_ROLE` / `_WAREHOUSE` / `_SCHEMA` | no | Empty = the user's defaults in Snowflake |
| `API_CORS_ORIGINS` | no | Browser origins allowed, comma-separated (default `http://localhost:5173`) |
| `KAFKA_BOOTSTRAP_SERVERS` | yes | Kafka broker `host:port` (plain, no login), e.g. `16.16.254.130:9092` |
| `KAFKA_TELEMETRY_TOPIC` / `KAFKA_REEFER_TOPIC` | yes | `fleet.silver.telemetry.v1` / `fleet.silver.reefer.v1` |
| `STREAM_HISTORY_MINUTES` | no | Minutes of live data kept (default 60): read back from Kafka on start, rows with an older `event_ts` are dropped |

## Endpoints
| Endpoint | Returns |
|---|---|
| `GET /health` | `{status, login_user, role, warehouse, database, schema}` as Snowflake sees the session |
| `GET /api/tables` | One row per table or view the user can see: `TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ROW_COUNT` |
| `GET /api/kpis/{dashboard_id}?kpi_ids=1&kpi_ids=2…` | One dashboard: KPI cards (`value`, `previous`) + chart `series`, last 30 days vs previous 30 days (see below) |
| `GET /api/stream` | Server-Sent Events: `telemetry`, `reefer`, `alert`, `kpis`, `stream_kpis`. Snapshot first, then changes. `?events=stream_kpis` sends only the listed events (see "Live stream" below) |

Any Snowflake failure (login, SQL, timeout) returns HTTP 503 with the Snowflake message in `detail`. An unknown `dashboard_id` returns 404.

## Flow
Clean architecture: each layer only calls the layer below it, and services depend on contracts, not on Snowflake.
Full explanation, every file, and how to add an endpoint: [ARCHITECTURE.md](ARCHITECTURE.md).
```
browser ──> api/routes/*.py          HTTP only (URL, response schema)
              └─> services/*.py      logic, depends on domain/repositories.py (contracts)
                    └─> infrastructure/repositories/snowflake_*.py   implements the contracts
                          ├─> infrastructure/sql_loader.py           reads queries/{kpis,series}/*.sql
                          └─> infrastructure/snowflake_client.py     fetch_all(sql, params) ──> Snowflake
                                └─> core/config.py                   settings (backend/.env)
```
- `core/config.py`: reads `.env` once; fails at startup with the list of missing variables.
- `infrastructure/snowflake_client.py`: one shared connection, opened on first query and reopened if Snowflake closed it. `fetch_all()` returns rows as dicts. If the login expired (`ReauthenticationRequest`, or error 390111 / 390112 / 390114), it opens a new connection and runs the query once more.
- `services/kpi_service.py`: the period, which SQL file each KPI and chart uses (`KPI_QUERIES`, `DASHBOARD_SERIES`), and what is not in the warehouse.
- `schemas/`: the exact response fields shown in `/docs`.

## Live stream (`GET /api/stream`)
Shapes: `TelemetryRow`, `ReeferRow`, `AlertRow`, `LiveKpis`, `StreamKpis` in [../dashboard/src/data/contract.js](../dashboard/src/data/contract.js).
```
Kafka fleet.silver.telemetry.v1 + fleet.silver.reefer.v1
  └─> infrastructure/kafka_stream_source.py   one aiokafka consumer, no group, reads back 2 x STREAM_HISTORY_MINUTES + 30 min on start
        └─> services/stream_service.py         background reader + 1-second send loop + one queue per viewer
              └─> services/fleet_state.py      latest row per vehicle_id, alerts, live KPIs (plain logic, no Kafka)
                    ├─> services/stream_history.py  every row (KPI columns only) of 2 x STREAM_HISTORY_MINUTES + 30 min
                    ├─> services/stream_kpis.py     stream KPIs + charts from those rows (plain functions)
                    └─> api/routes/stream.py   SSE: snapshot first, then the changes of each tick (?events= filter)
```
- **The data today:** the silver job publishes a batch every ~5 min (one row per truck; ~2,150 telemetry + ~1,180 reefer rows), and the newest reading is ~10 min old when it arrives. Nothing in the code depends on the 5 min: every rule uses `event_ts`.
- **Duplicates and late rows:** a row is kept only if its `event_ts` is newer than the truck's stored row (duplicates are ~0.4%, same `event_ts`). This also makes reading the history again (restart, Kafka retry) safe.
- **History:** rows with `event_ts` older than `STREAM_HISTORY_MINUTES` are dropped every second; their active alerts end at the row's last `event_ts`.
- **Alerts:** active while the flag is true in the truck's latest row: `is_speeding` → `SPEEDING`, `is_engine_overheating` → `ENGINE_OVERHEATING`, `is_low_fuel` → `LOW_FUEL`, `is_temp_breach` → `COLD_CHAIN_BREACH`, `is_reefer_unit_failure` → `REEFER_UNIT_FAILURE`. `EXCESSIVE_IDLING`: `is_idling` for ≥ 30 min by `event_ts` (catalog KPI 34). `anomaly_id` = `vehicle_id-anomaly_type-start_ts`.
- **Sending:** every second, only if something changed (with a 5-min batch: one send per batch). A new viewer gets every row, active alerts, the last 40 alert changes and the KPIs first.
- **Kafka down:** the reader logs the error and tries again every 10 s; the API keeps serving the data it has.
- **Stream KPIs (`stream_kpis`):** KPIs 10, 11, 12, 13, 14, 15, 16, 23, 29, 33, 34 and the charts `trip_temperature`, `excursions_by_trailer`, `excursion_rate_by_ambient`, `high_risk_trips`, `time_in_state`, calculated from **every** Kafka row of the last 60 min of `event_ts` (ending at the newest row) vs the 60 min before. Same shapes as `GET /api/kpis/{dashboard_id}`, where they are `null`.
  - Platform KPIs in the same event, from the Kafka messages themselves (`services/platform_stats.py`), last 60 min of **Kafka time** vs the 60 before (Kafka time because a broken message has no `event_ts`): **54** messages per second, **57** duplicates (same `vehicle_id` + `event_ts` as a kept row) %, **58** rejected (not JSON, or no valid `vehicle_id` / `event_ts`) %, **60** now − newest Kafka time (min). A message read again after a Kafka failure (same partition + offset, Kafka time not newer) is skipped, so it is never counted as a duplicate. `stream_kpis` is also sent every minute, so KPI 60 keeps growing between batches. Measured 2026-10-29 13:45 UTC: 54 = 11.17 events/s, 57 = 0.4 %, 58 = 0.0 %, 60 = 0.1 min.
  - Rows kept: only the columns the KPIs read, for 2 × 60 min + a 30-min margin (~100k rows = ~42 MB, measured 2026-10-29; full rows would be ~223 MB for 120 min). Calculated once per Kafka batch (~0.8 s), event ~1 KB.
  - Rules: a row counts until the next row of its truck/trailer, at most 15 min (`INTERVAL_CAP`). Excursion = ≥ 2 consecutive `is_temp_breach` rows of one trailer (null `cargo_temp_f` skipped). Excessive idling (KPI 34) counts when `is_idling` reaches 30 min, like the alert. A run that begins with the first kept row is skipped (its start is unknown); the 30-min margin keeps the previous window complete.
  - Assumptions: no `trip_id` / `load_id` in Kafka, so one trailer (reefer) or truck (telemetry) in the window = one trip (KPIs 11, 15, 16); KPI 29 = `DRIVING` time / all time (no loading/unloading in Kafka); KPI 15 uses the silver flag `is_reefer_unit_failure`.
  - KPI 17 has no card (only per band, in the chart). Removed from the dashboard (no data source): KPI 35 (no route in Kafka), 51–53 (labels only in S3), `kpi_33`/`kpi_34` per driver (no `driver_id`), weekly `kpi_11` (Kafka keeps ~13 h).

## Dashboard KPIs (`GET /api/kpis/{dashboard_id}`)
Shape: `DashboardResponse` in [../dashboard/src/data/contract.js](../dashboard/src/data/contract.js). The dashboard sends the page's KPI ids (from `dashboard/src/dashboards.js`).
- **Period:** 30 days ending **yesterday** (`DATA_LAG_DAYS = 1`) vs the 30 days before. Each row counts on the day it happened (`ACTUAL_DATE`, `PURCHASE_DATE`, `MAINTENANCE_DATE`, `INCIDENT_DATE`, snapshot date). Trips count on the day they **finished** (`ARRIVAL_TS::DATE`): a trip lands in `FCT_TRIPS` only when completed, so by start day (`TRIP_DATE`) the last days would be incomplete.
- **Units:** metric, as the marts store them: km, L, L/100km, USD.
- **Not in the warehouse → `null`:** stream KPIs 10–16, 23, 29, 33, 34 and their charts (they come in the `stream_kpis` event of `GET /api/stream` instead) and platform KPIs 54, 57, 58, 60 (also in `stream_kpis`). KPI 65 Warehouse Data Freshness (`warehouse_data_freshness.sql`: now − newest `_AIRBYTE_EXTRACTED_AT` over the 13 `RAW_DATA` tables, min, no previous) is a warehouse KPI. The live page has no KPI cards, so `live` is not a dashboard id here (404).
- **No cache:** every call runs the SQL (one dashboard ≈ 2–4 s). The KPI logic is meant to move to dbt later.
- **SQL:** one file per KPI in `queries/kpis/` (returns `PERIOD` = `value`/`previous` + `KPI_VALUE`), one per chart in `queries/series/`. Parameters: `%(previous_start)s`, `%(current_start)s`, `%(current_end)s`. Never write a `%` sign in these files (the connector reads `%` as a parameter): write "pct".
- Table names are not schema-qualified, so `SNOWFLAKE_API_SCHEMA` must be `DBT_MARTS`. Only KPI 22 and its two charts read `RAW_DATA.DIESEL_PRICES` (not in the marts yet).

| KPI | Formula (SQL file in `queries/kpis/`) |
|---|---|
| 1 On-Time Delivery Rate (%) | DELIVERY events with `on_time_flag = 'TRUE'` / all DELIVERY events × 100 |
| 2 On-Time Pickup Rate (%) | same for PICKUP events |
| 3 Average Delivery Delay (min) | AVG `delay_minutes` of late deliveries only (`delay_minutes > 0`) |
| 5 Severe Delay Rate (%) | DELIVERY events with `delay_minutes > 120` (assumption) / all DELIVERY events × 100 |
| 6 Destination Queue Time (min) | AVG of delivery `actual_datetime` − trip `arrival_ts` |
| 7 Dock Time (min) | AVG `detention_minutes`, pickups and deliveries |
| 8 Trip Duration Variance (%) | AVG per trip of (`actual_duration_hours` − planned) / planned × 100; planned = scheduled delivery − scheduled pickup |
| 19 Total Fuel Spend (USD) | SUM fuel purchase `total_cost` |
| 20 Fuel Cost per km (USD/km) | SUM `fuel_liters_used` × period price per liter (SUM `total_cost` / SUM `liters` of purchases) / SUM km |
| 21 Fuel Efficiency (L/100km) | AVG `average_l_per_100km` |
| 22 Fuel Price Variance (%) | AVG per purchase of (`price_per_liter` − national price that day) / national × 100 |
| 24 Idle Time Share (%) | SUM `idle_time_hours` / SUM `actual_duration_hours` × 100 |
| 26 Revenue per km (USD/km) | SUM (revenue + surcharge + accessorials) / SUM km |
| 27 Fuel Cost % of Revenue (%) | fuel cost (as KPI 20) / revenue × 100 |
| 28 Margin Proxy per Trip (USD) | AVG per trip of revenue − fuel cost (as KPI 20) − truck's period maintenance allocated by km; trips without truck excluded |
| 30 Km per Truck per Day (km) | SUM trip km / truck-days (`FCT_TRUCK_DAILY` rows) |
| 36 Incident Rate (per 1M km) | incidents × 1,000,000 / SUM trip km |
| 38 Claim Cost (USD) | SUM `claim_amount` |
| 41 Total Maintenance Cost (USD) | SUM `total_cost` |
| 42 Maintenance Downtime (h) | SUM `downtime_hours` |
| 43 Orders per Truck (orders) | maintenance orders / distinct trucks in `FCT_TRUCK_DAILY`, per 30 days |
| 44 Maintenance Cost per km (USD/km) | SUM maintenance `total_cost` / SUM trip km |
| 46 Truck Availability (%) | truck-days with `is_in_maintenance = FALSE` / all truck-days × 100 |
| 65 Warehouse Data Freshness (min) | now − newest `_AIRBYTE_EXTRACTED_AT` over the 13 `RAW_DATA` tables (no previous) |
