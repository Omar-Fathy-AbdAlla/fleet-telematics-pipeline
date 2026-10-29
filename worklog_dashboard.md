# Fleet Dashboard: Work Summary



---

## 1. Summary

I built a web dashboard for a truck fleet of **5,000 trucks**. It has two kinds of data:

| Kind | Source | How it reaches the screen | How fresh |
|---|---|---|---|
| **History KPIs** (deliveries, fuel, safety, maintenance) | Snowflake data warehouse (`DBT_MARTS`) | Backend runs SQL → REST API → page | Refreshed every 30 min |
| **Live data** (truck positions, alerts, live KPIs) | Kafka (2 streaming topics) | Backend keeps the latest state in memory → pushes it to the browser (SSE) | Pushed as soon as a new batch arrives (every 5 min) |

The result: **8 dashboard pages + 1 KPI guide page**, **40 KPIs**, **22 charts**, and a **3D live map of the USA** that shows every truck.
The dashboard does no KPI math: every number is calculated in the backend, so the logic lives in one place.

---

## 2. What the dashboard shows

| Page | Who uses it | KPI cards | Data source |
|---|---|---|---|
| Live Fleet Map | Operations | 11 live tiles + alert feed | Kafka (live) |
| Executive Overview | Management | 7 | Warehouse + Kafka |
| Delivery & Route Performance | Dispatch, customer service | 7 | Warehouse |
| Cold Chain Monitoring | Cold-chain quality | 7 | Kafka |
| Fuel & Cost | Fleet finance | 8 | Warehouse + Kafka |
| Fleet Utilization & Driver Safety | Fleet safety | 6 | Warehouse + Kafka |
| Maintenance & Reliability | Maintenance managers | 5 | Warehouse |
| Data Platform Health | Data engineers | 5 | Kafka + warehouse |
| KPI Guide | Everyone | – | Text only: name, unit, meaning and formula of every KPI |

**Where the 40 KPIs come from:**

| Source | KPIs | Count |
|---|---|---|
| Warehouse (SQL in Snowflake) | 1, 2, 3, 5, 6, 7, 8, 19, 20, 21, 22, 24, 26, 27, 28, 30, 36, 38, 41, 42, 43, 44, 46, 65 | 24 |
| Kafka stream (calculated in the backend) | 10–17, 23, 29, 33, 34 | 12 |
| Kafka messages (platform health) | 54, 57, 58, 60 | 4 |

Every card shows the **current period** and the **change vs the previous period** (▲▼):
- warehouse KPIs: last 30 days vs the 30 days before;
- stream KPIs: last 60 min vs the 60 min before.

---

## 3. System architecture

```
                 ┌──────────────────── Backend (Python, FastAPI) ────────────────────┐
 Snowflake       │                                                                    │
 DBT_MARTS ─────►│  KPI service: one SQL file per KPI / chart ──► GET /api/kpis/{page} │──REST──┐
                 │                                                                    │        │
 Kafka           │  Stream service: reads both topics ──► fleet state in memory       │        ▼
 telemetry ─────►│     (latest row per truck, alerts, live KPIs, stream KPIs)         │     Browser
 reefer    ─────►│     ──► GET /api/stream (Server-Sent Events, pushed)               │──SSE──►(React)
                 └────────────────────────────────────────────────────────────────────┘
```

**Backend layers (clean architecture):** each folder has one job, so the code stays easy to change as the number of KPIs grows.

| Layer | Job |
|---|---|
| `api/` | URLs and the response shape |
| `services/` | The logic: what to calculate |
| `domain/` | Contracts: which data functions exist (no Snowflake, no Kafka) |
| `infrastructure/` | Real data access: Snowflake connection, SQL files, Kafka reader |
| `schemas/` | Exact JSON shape of each response |
| `core/` | Settings (`.env`) and error handling |

Rule: the logic never talks to Snowflake or Kafka directly, only through a contract. This makes it testable with fake data.

**Frontend layers:** pages → hooks (`useKpis`, `useStream`) → one data file (`apiSource.js`) → backend.
Pages never call the backend themselves, so the URLs live in one file.

### Technology choices

| Part | Tool | Why |
|---|---|---|
| Frontend | React + Vite + Tailwind | Fast to build, one component per card / chart |
| Charts | Recharts | Simple React charts |
| 3D map | Three.js (react-three-fiber) | Draws 5,000 trucks smoothly in the browser |
| US map borders | `us-atlas` file bundled with the app | No map service, no API key |
| Backend | FastAPI (Python) | Same language as the data team, built-in API docs and SSE |
| Kafka client | aiokafka | Runs in the same async loop as FastAPI |
| Live push | Server-Sent Events (SSE) | One-way server → browser is all we need; simpler than WebSockets |

---

## 4. Work done, step by step

### Step 1: Start early with mock data (2026-10-26)
The warehouse and the stream were not ready, so I built the dashboard on **fake (mock) data** behind one switchable data source.
This let me design all the pages first. The real backend was plugged in later without touching the pages.

### Step 2: 3D map of the USA (2026-10-26)
- I searched for a free 3D truck model (`truck_toyota_corsa_b.glb`) and used it for every truck.
- I drew the US state borders from the `us-atlas` file (lower 48 states).
- All trucks are drawn as **one instanced mesh**: one model drawn up to 10,000 times in a single draw call. This keeps 5,000 trucks smooth.
- Trucks glide from their old to their new position, turn to their heading, and are colored by status (driving, idling, parked, alert).

### Step 3: KPIs planned by the team, applied in the dashboard (2026-10-26)
The team agreed on the KPI catalog and the 7 dashboards ([Notion_Data_Catalog.md](Notion_Data_Catalog.md)).
I turned it into one registry of pages ([dashboards.js](dashboard/src/dashboards.js)) and one file with the text of every KPI ([definitions.js](dashboard/src/kpis/definitions.js)). The backend only sends numbers.

### Step 4: Backend and connection tests (2026-10-28 → 2026-10-29)
- Built the FastAPI backend with a `/health` check and a table listing, to prove the Snowflake login works.
- Tested the Kafka connection and measured the real stream before designing anything (batch size, timing, duplicates).

### Step 5: Data checks on the warehouse (2026-10-29)
I wrote a check script ([tools/validate_marts.py](tools/validate_marts.py)) that runs **53 checks** on the warehouse tables (keys that point to nothing, duplicate keys, empty keys).
Result: **40 PASS, 9 WARN, 4 FAIL**. The model structure is sound. I found **4 root causes** and reported them to the model owner in [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md), for example:
- `FCT_MAINTENANCE.FACILITY_KEY` is empty in 100% of rows (106,524 rows), a dbt model bug;
- about 2% of trips have no truck in the source data.

### Step 6: Backend restructured into layers (2026-10-29)
I split the backend into the layers of section 3, so it can serve all 8 pages and the stream.
Check: the responses before and after were **byte-for-byte identical**.

### Step 7: Warehouse KPI queries + 30-min refresh (2026-10-29)
- Wrote **24 SQL files** (one per KPI) and **17 SQL files** (one per chart). They run in Snowflake on the last 30 days vs the 30 days before.
- The dashboard asks again every **30 min** to pick up new data.
- Units are metric everywhere (km, L, L/100 km, USD/km).
- **Problem found and fixed:** trips are saved only when they finish (59 h on average). Counting them on their start day made the last days look ~3–4% low. They are now counted on the day they finished.

### Step 8: Live stream from Kafka (2026-10-29)
We planned the full streaming flow together first ([STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md)). Then I built it:
1. The backend reads both Kafka topics (`telemetry`, `reefer`).
2. It keeps the latest row of every truck in memory and drops duplicate or late rows.
3. It creates alerts from the row flags: speeding, engine overheating, low fuel, cold-chain breach, reefer failure, and idling for more than 30 min.
4. Every second it sends only what changed to every open browser (SSE).
5. A new viewer first gets a full snapshot (all trucks + active alerts + KPIs).

### Step 9: Mock data removed (2026-10-29)
After the real backend worked, I deleted all mock data (6 files, 746 lines). The dashboard now reads only the backend.

### Step 10: Stream KPIs, platform KPIs, KPI clean-up (2026-10-29)
- **Stream KPIs:** the cold-chain, idling, speeding and driving-time KPIs need telemetry, which the warehouse does not have. The backend now calculates them from Kafka (last 60 min vs the 60 min before).
- **Platform KPIs:** throughput, duplicate rate, rejection rate and freshness of the stream (54, 57, 58, 60), plus a new KPI 65 (warehouse data freshness).
- **Removed:** 11 KPIs and 3 charts that **no data source** can fill (for example detection precision, pipeline success rate). Showing an empty card forever is misleading.

### Step 11: Live page highlights (2026-10-29)
When a live value changes, its tile or alert row lights up for **2 s**, so the user sees what is new.

### Step 12: Cairo time
Data stays in UTC, but every time on the screen is shown in **Cairo time** (summer time included): live map, alerts, "last updated", cold-chain chart, stream KPI period, "delay by hour" chart.
Cairo is the default, so the times show without a "Cairo" label.

### Step 13: Stream KPIs on the pages (2026-10-29)
Every page now fills its stream KPI cards and charts from the live `stream_kpis` event (step 2 of [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md)). Pages without the map ask only for that event (~3 KB instead of ~4 MB).
A bug found in the browser test was fixed: the browser keeps left pages open in its back/forward cache with their live connection, and allows only 6 connections per host, so after a few reloads the backend seemed stuck. The page now closes its connection when it is left.

### Step 14: Live map facilities and filters (2026-10-29)
- The **50 facilities** are drawn as small buildings; hover shows the name and city. Their positions and the map area are read once from the warehouse ([tools/export_map_data.py](tools/export_map_data.py)).
- A parked truck within **10 mi** of a facility is "Parked at facility"; farther away it is "Resting on route" (the driver's rest break).
- The map legend is clickable: click a status to hide or show those trucks. The Delivery lane map has the same filters (on-time band, origin city).

### Not done yet
- Trucks glide continuously between their Kafka rows (step 3 of [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md)). Today they move once per 5-min batch.

---

## 5. Key decisions and why

| Decision | Why |
|---|---|
| The backend calculates every KPI; the browser only shows them | One place for the logic; the same number everywhere |
| One SQL file per KPI and per chart | Easy to read, test in Snowflake and later move into dbt |
| SSE instead of WebSockets | Data only goes server → browser; SSE is simpler and reconnects by itself |
| Fleet state kept in memory, no Redis | 5,000 trucks fit easily; no extra service to run |
| Kafka read without a consumer group | Every backend instance must see every truck; history is read again on start (60 min) |
| Warehouse window ends yesterday | Today is still loading, so its numbers would look too low |
| KPIs with no data source removed | An empty card forever is misleading |
| No `trip_id` in Kafka → one trailer/truck in the window = one trip | Written down as an assumption |

---

## 6. Tests and results

| Test | Result | Meaning |
|---|---|---|
| Warehouse KPI SQL (24 KPIs + 17 charts) on Snowflake | All run; 4.5 s for all KPIs, 9.5 s for all charts | The queries are fast enough to run on demand |
| KPI endpoint for all pages | 200 OK, 0.2–1.6 s per page | A page loads in under 2 s |
| Stream logic with fake data | **51 checks, all pass** (values worked out by hand) | The rules are correct on known inputs |
| Real Kafka | 5,000 trucks (3,543 parked / 1,215 driving / 242 idling), 234 active alerts | The live map shows the real fleet |
| Snapshot size for a new viewer | 4.1 MB, first byte in 0.66 s | OK on a local network; to reduce for remote users |
| Stream KPI calculation | 0.65–0.85 s per batch, event 0.9 KB | Light enough to run on every 5-min batch |
| Stream throughput (KPI 54) | 11.17 events/s | Kafka sends ~40,000 messages per hour |
| Duplicate rate (KPI 57) | 0.4 % | Few repeated rows; the backend drops them |
| Highlight test in a headless browser | Page load: 0 tiles lit; new batch: tiles lit for 2.1 s | The highlight works only on real changes |
| Stream KPIs on the pages, headless browser | 11 page changes + 9 full reloads: all cards filled, 0 connections left open | The 6-connection bug is fixed |
| Frontend build | `npm run build` passes (also after the facilities / filter step) | No build errors |

**Sample warehouse KPIs** (30 days, 2026-09-27 to 2026-10-26, vs the 30 days before):

| KPI | Current | Previous | Meaning |
|---|---|---|---|
| On-Time Delivery (%) | 93.27 | 93.39 | 93 of 100 deliveries arrive on time |
| Average Delivery Delay (min) | 170.4 | 174.4 | A late delivery is ~2.8 h late on average |
| Fuel Efficiency (L/100 km) | 36.27 | 36.24 | = 6.5 mpg, inside the normal 5.8–7.8 mpg for trucks |
| Total Fuel Spend (USD) | 29,023,609 | 29,688,871 | Fuel bought in 30 days |
| Incident Rate (per 1M km) | 0.756 | 0.689 | Near the expected industry level |
| Truck Availability (%) | 97.90 | 97.91 | ~2% of trucks are in maintenance |

---

## 7. Problems met and how they were solved

| Problem | Fix |
|---|---|
| Last days of trip KPIs looked too low | Count trips on the day they finished, not the day they started |
| Snowflake login expired after some hours | The backend opens a new connection and retries once |
| Kafka port was blocked | The owner opened port 9092 |
| A Snowflake division kept only 6 decimals (KPI 36 gave exactly 1.0) | Multiply by 1,000,000 before dividing |
| All 40 alert rows lit up on page load | Mark an alert as "new" when its message arrives, not when React draws it |
| Backend seemed stuck after a few page reloads | The browser's back/forward cache kept old live connections open (6 per host max); the page now closes its connection when left |
| Data errors in the warehouse model | Found with the 53-check script, reported to the model owner |

---

## 8. Where to read more

| Document | Content |
|---|---|
| [WORK_LOG.md](WORK_LOG.md) | Every step in detail: files changed, tests, numbers |
| [dashboard/README.md](dashboard/README.md) | Frontend: every file, page, chart and the 3D map |
| [backend/README.md](backend/README.md), [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md) | Backend: endpoints, KPI formulas, layers, data flow |
| [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md) | The streaming plan and its decisions |
| [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md) | The warehouse data check and its findings |
| [RUN.md](RUN.md) | How to run the backend and the dashboard |
