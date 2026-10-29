# 🚛 Fleet Data Platform

An end-to-end data engineering pipeline built on a simulated US trucking fleet (5,000 Class-8 trucks by default).
A Python generator produces realistic, intentionally dirty data. The platform ingests, cleans and models it, then serves it to a web dashboard.

**Team:** Mohamed Bedier, Omar Fathy, Karim Mohamed, Mohamad Farah
**Program:** Samsung Innovation Campus (SIC 8): Big Data graduation project

### Documents (read in this order)
| # | Document | What it contains |
|---|---|---|
| 1 | **README.md** (this file) | The whole platform: architecture, data, warehouse, progress |
| 2 | [worklog_dashboard.md](worklog_dashboard.md) | **Summary of the dashboard work:** pages, architecture, steps, decisions, tests, problems solved |
| 3 | [RUN.md](RUN.md) | How to start the application locally (backend + dashboard), checks, and common problems |
| 4 | [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md) | 53 data checks on the warehouse marts, results and root causes |
| 5 | [WORK_LOG.md](WORK_LOG.md) | Detailed log of the dashboard: every step, file, decision and test |
| 6 | [backend/README.md](backend/README.md), [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md) | Backend: endpoints, KPI formulas, layers, data flow |
| 7 | [dashboard/README.md](dashboard/README.md) | Frontend: every file, page, chart and the 3D map |
| 8 | [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md) | Plan and decisions for the KPIs calculated from Kafka |
| 9 | [PIPELINE_WORK_LOG.md](PIPELINE_WORK_LOG.md) | Snowflake account + Airbyte setup and the S3 bucket survey |
| 10 | [Notion_Data_Catalog.md](Notion_Data_Catalog.md) | All 16 tables and their columns, S3 layout, data quality notes, the KPI catalog, dashboards, generator Q&A (Notion export) |
| 11 | [Notion_Documentation.md](Notion_Documentation.md) | Team setup log: EC2, Kafka, IAM, S3 (Notion export; images are only in the live page) |
| – | [Notion: Data Catalog](https://app.notion.com/p/Data-Catalog-404961599a4880f6898eea33b93d731d) / [Notion: Documentation](https://app.notion.com/p/Documentation-3ff961599a4880dc9232c35ae49c5409) | Live sources of the two Notion exports |

---

## 1. Architecture

There are two paths, both fed by the same generator:

```
                          fleet_generator.py  (AWS EC2, 24/7)
               ┌────────────────────┴────────────────────┐
          batch CSV.gz                              Kafka (raw topics)
      (every 15 min) + JSON refs                         │
               │                              Spark Structured Streaming (silver job)
               ▼                                         │
         Amazon S3 (Bronze)                    Kafka silver topics
               │                     fleet.silver.telemetry.v1 / fleet.silver.reefer.v1
               ▼                                         │  one batch every ~5 min
            Airbyte                                      │
               ▼                                         │
   Snowflake SUPPLYCHAIN_DW                              │
   RAW_DATA ──dbt──► DBT_MARTS                           │
               │                                         │
               └────────► Backend API (FastAPI) ◄────────┘
                    REST /api/kpis       SSE /api/stream
                                   │
                                   ▼
                 Web dashboard (React): 8 pages + live 3D map
```

| Path | Purpose | How fresh | Source of the numbers |
|---|---|---|---|
| **Batch** (S3 → Airbyte → Snowflake → dbt → backend → dashboard) | History KPIs: delivery, fuel, safety, maintenance | Dashboard refreshes every 30 min | Snowflake `DBT_MARTS` (24 KPIs, 17 charts) |
| **Speed** (Kafka → Spark → Kafka silver → backend → dashboard) | Live truck positions, alerts, cold-chain, idling and platform KPIs | Pushed when a Kafka batch arrives (~5 min) | Kafka silver topics (16 KPIs, 5 charts) |

> **Rule:** every KPI has one source only. Warehouse KPIs come from Snowflake, stream KPIs from Kafka. The backend calculates every KPI; the dashboard only shows them.

### Tools
| Tool | Role |
|---|---|
| Python | Data generator (`fleet_generator.py`) |
| AWS EC2 | Runs the generator and Kafka 24/7 (Ubuntu 24.04, `c7i-flex.large`) |
| Apache Kafka 4.3.1 | Streaming broker (KRaft) |
| Kafka Connect | Sinks raw telemetry from Kafka to S3 |
| Spark Structured Streaming | Cleans the raw stream and publishes the silver topics |
| AWS S3 | Data lake (Bronze / raw layer) |
| Airbyte | Moves the CSV files from S3 to Snowflake `RAW_DATA` |
| Snowflake | Data warehouse |
| dbt | Cleaning and modeling: `RAW_DATA` → `DBT_MARTS` (facts and dimensions) |
| FastAPI (Python) | Backend API: warehouse KPIs over REST, live stream over Server-Sent Events |
| React + Vite + Three.js | Web dashboard and the 3D live map |

---

## 2. Data in S3 (Bronze)

Bucket `fleet-telematics-lakehouse-team11`, region `eu-north-1`.
Partitions use `dt=YYYY-MM-DD` and `hr=HH` (UTC). Files are named `{entity}-{run_id}-{sequence}.csv.gz`.

| S3 path | Tables | Format |
|---|---|---|
| `fleet/bronze/registry/{trucks,trailers}/` | trucks, trailers (daily snapshots) | CSV.gz |
| `fleet/bronze/hr/drivers/` | drivers (daily snapshot) | CSV.gz |
| `fleet/bronze/tms/{customers,facilities,routes,loads,trips,delivery_events}/` | TMS exports | CSV.gz |
| `fleet/bronze/fuel_card/fuel_purchases/` | fuel_purchases | CSV.gz |
| `fleet/bronze/cmms/maintenance_records/` | maintenance_records | CSV.gz |
| `fleet/bronze/safety/safety_incidents/` | safety_incidents | CSV.gz |
| `fleet/bronze/prices/diesel_prices/` | diesel_prices | CSV.gz |
| `fleet/bronze/weather/open_meteo/` | raw Open-Meteo responses | JSON.gz |
| `bronze/telemetry.raw/dt=/hour=/` | telemetry sunk by Kafka Connect | JSON lines (uncompressed) |
| `fleet/silver/telemetry/` | telemetry written by Spark | Parquet |
| `fleet/ground_truth/gen_anomaly_labels/` | injected anomaly labels (evaluation only) | JSONL.gz |

> ⚠️ The Kafka Connect folder sits at the bucket root (`bronze/…`), not under `fleet/`, and uses `hour=` instead of `hr=`.

Folder sizes and samples (bucket survey, 2026-10-27): [PIPELINE_WORK_LOG.md](PIPELINE_WORK_LOG.md), step 4c. Full column definitions: [Notion_Data_Catalog.md](Notion_Data_Catalog.md), section 3.

---

## 3. Snowflake (team warehouse)

| Object | Name | Notes |
|---|---|---|
| Database | `SUPPLYCHAIN_DW` | In a teammate's Snowflake account |
| Schema | `RAW_DATA` | 13 tables loaded by Airbyte from the S3 CSV folders (one per table), with the load time in `_AIRBYTE_EXTRACTED_AT` |
| Schema | `DBT_MARTS` | Built by dbt. Dimensions: `DIM_CUSTOMER`, `DIM_DATE`, `DIM_DRIVER`, `DIM_FACILITY`, `DIM_LOCATION`, `DIM_ROUTE`, `DIM_TRAILER`, `DIM_TRUCK`. Facts: `FCT_TRIPS`, `FCT_SHIPMENTS`, `FCT_DELIVERY_EVENTS`, `FCT_FUEL_PURCHASES`, `FCT_MAINTENANCE`, `FCT_SAFETY_INCIDENTS`, `FCT_TRUCK_DAILY` |
| Dashboard login | `AIRFLOW_USER`, role `AIRFLOW_ROLE`, warehouse `AIRBYTE_WH` | Read only. Values live in `backend/.env` (git-ignored) |

**Data check:** 53 checks on `DBT_MARTS` (orphan keys, duplicate keys, empty keys, one current row per history ID): **40 PASS, 9 WARN, 4 FAIL**, from 4 root causes reported to the model owner. Details: [MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md).

---

## 4. Repository layout

```
.
├── README.md                     # this file
├── RUN.md                        # how to run the backend and the dashboard
├── worklog_dashboard.md          # summary of the dashboard work
├── WORK_LOG.md                   # detailed log of the dashboard (backend + frontend)
├── PIPELINE_WORK_LOG.md          # Snowflake account + Airbyte setup, S3 bucket survey
├── MARTS_VALIDATION_REPORT.md    # data checks on DBT_MARTS
├── STREAM_KPIS_PLAN.md           # plan for the Kafka stream KPIs
├── Notion_Data_Catalog.md        # data catalog + KPIs + Q&A (Notion export)
├── Notion_Documentation.md       # team documentation (Notion export)
├── all_queries.sql               # all 41 backend SQL queries in one file (copy of backend/app/infrastructure/queries)
├── requirements.txt              # Python package for tools/s3_survey.py (boto3)
├── tools/
│   ├── s3_survey.py              # lists S3 folders and samples file headers
│   ├── validate_marts.py         # 53 checks on DBT_MARTS keys (PASS / WARN / FAIL)
│   ├── export_map_data.py        # writes the facilities + map area from DBT_MARTS to dashboard/src/data/facilities.js
│   └── build_env.sh              # builds the local .env from the secret files (prints no secret)
├── backend/                      # FastAPI: Snowflake KPIs + Kafka live stream (see backend/README.md)
└── dashboard/                    # React web dashboard (see dashboard/README.md)
```

---

## 5. Progress

| # | Part | Status |
|---|---|---|
| 1 | Generator + Kafka on EC2 | ✅ Done (see Notion Documentation 2.1–2.3) |
| 2 | S3 bucket (Bronze) + EC2 IAM role | ✅ Done |
| 3 | Airbyte: S3 → Snowflake `RAW_DATA` (13 tables) | ✅ Done (team warehouse) |
| 4 | dbt: `RAW_DATA` → `DBT_MARTS` | ✅ Done. Checked with 53 checks; 4 model issues reported ([MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md)) |
| 5 | Spark silver job → Kafka silver topics | ✅ Done |
| 6 | Backend API: warehouse KPIs (REST) + live stream (SSE) | ✅ Done (2026-10-29) |
| 7 | Web dashboard: 8 pages, 40 KPIs, 22 charts, 3D live map with facilities | ✅ Done (2026-10-29) |
| 8 | Live map replay: trucks glide between their Kafka rows | ⬜ Planned (step 3 of [STREAM_KPIS_PLAN.md](STREAM_KPIS_PLAN.md)) |

---

## 6. Open items

1. **Data model:** 4 questions wait for the model owner ([MARTS_VALIDATION_REPORT.md](MARTS_VALIDATION_REPORT.md), section 4).
2. **Notion page:** still says bucket `supply-chain-graduation-project` / `us-east-1`. The live bucket is `fleet-telematics-lakehouse-team11` in `eu-north-1`.
3. **Reefer stream in S3:** there is no Kafka Connect folder for the reefer topic, only `telemetry.raw` (bucket survey, 2026-10-27).
4. **Topic and folder naming:** the topics are `fleet.telemetry.v1` but the S3 folder is `telemetry.raw`. Agree on one scheme.
5. **`DIRECT_S3_PCT`:** trucks that write directly to S3 never reach Kafka, so they are missing from the live map. Set it to 0, or document this.
6. **Dashboard:** KPIs 60 and 65 have no previous value, so their card says "no change vs previous"; the high-risk trips table has a `trip_id` column that is always `-` (Kafka has no `trip_id`).

---

## 7. Security rules

- Never commit or paste passwords, AWS keys, Snowflake private keys or tokens. Use `<YOUR_KEY>` in docs and blur screenshots.
- Each tool gets its own least-privilege identity: EC2 instance role (writes to S3), Airbyte's read access to the bucket, the backend's read-only Snowflake login.
- Secrets live outside the repository (`~/.aws/credentials`, `~/.snowflake_keys/`) or in git-ignored `.env` files.
- `.gitignore` blocks `*.pem`, `*.p8`, `*.pub`, `.env`, `.env.*` and `profiles.yml`.
- If a key is exposed, deactivate and replace it in IAM immediately.
