# Fleet Data Platform: Complete Reference

**Source:** Notion page "Data Catalog": https://app.notion.com/p/Data-Catalog-404961599a4880f6898eea33b93d731d
**Exported:** 2026-10-26, through Notion's public page API (961 blocks)
**Contents:** Part A is a summary. Part B is the full page content: Data Catalog, KPIs, Q&A.

---

# Part A: Summary

## A.1 What the project is
- `fleet_generator.py` simulates a US trucking fleet (5,000 Class-8 trucks by default). It runs continuously and produces raw data the way real source systems would.
- The data is realistic:
  - Trucks follow Hours-of-Service (HOS) rules.
  - Trucks refuel when the tank reaches 18%.
  - The reefer (refrigerated trailer) model uses real Open-Meteo weather.
  - Diesel prices come from the EIA, or from a labelled model when no API key is set.
- Dirty data is added on purpose. Anomalies are injected, and their labels are kept as ground truth.
- Planned stack: **S3 (Bronze)**, then **Airbyte** into **Snowflake** (RAW, then STAGING, then MARTS). **dbt** handles transformations, **Airflow** handles scheduling, and **Power BI** shows the dashboards.
- Project setting: Kafka is not used (`KAFKA_MODE=null`, `DIRECT_S3_PCT=100`), so all stream data goes directly to S3 as JSONL.gz.

## A.2 Data sources at a glance
| Category | Tables | Format | S3 path |
|---|---|---|---|
| Master | trucks, trailers, drivers (daily snapshots); customers, facilities, routes | CSV.gz / 15 min | `bronze/registry/`, `bronze/hr/`, `bronze/tms/` |
| Reference | diesel_prices; raw Open-Meteo and EIA responses | CSV.gz / JSON.gz | `bronze/prices/`, `bronze/weather/open_meteo/` |
| Transaction | loads, trips, delivery_events, fuel_purchases, maintenance_records, safety_incidents | CSV.gz / 15 min | `bronze/tms/`, `bronze/fuel_card/`, `bronze/cmms/`, `bronze/safety/` |
| Streaming | telemetry, reefer | JSON (Kafka) or JSONL.gz / 10 min | `bronze/stream_direct/{telemetry,reefer}/` |
| Ground truth | gen_anomaly_labels | JSONL.gz | `ground_truth/gen_anomaly_labels/` |

Every folder is partitioned by `dt=YYYY-MM-DD/hr=HH` (UTC). Files are named `{entity}-{run_id}-{sequence}.csv.gz`.

## A.3 Primary keys
| Table | Primary key | ID format |
|---|---|---|
| trucks | truck_id (+ snapshot_date) | TRK00001 |
| trailers | trailer_id (+ snapshot_date) | TRL00001 |
| drivers | driver_id (+ snapshot_date) | DRV00001 |
| customers | customer_id | CUST00001 |
| facilities | facility_id | FAC00001 |
| routes | route_id | RTE00001 |
| diesel_prices | effective_date | - |
| loads | load_id | LOAD00000001 |
| trips | trip_id | TRIP00000001 |
| delivery_events | event_id | EVT00000001 |
| fuel_purchases | fuel_purchase_id | FUEL000000001 |
| maintenance_records | maintenance_id | MAINT00000001 |
| safety_incidents | incident_id | INC00000001 |
| telemetry | event_id | `T00001<epoch>` |
| reefer | event_id | `R00001<epoch>` |
| gen_anomaly_labels | anomaly_id | A00000001 |

## A.4 Relationship model
```
customers ─┐            ┌─ drivers
routes ────┴─> loads <── trips ──┬─ trucks <── telemetry (vehicle_id + time window)
                 ^         │     ├─ trailers <── reefer (trailer_id + time window)
                 │         │     └─ (trip_id) fuel_purchases, safety_incidents, gen_anomaly_labels
                 └── delivery_events ──> facilities
trucks <── maintenance_records, fuel_purchases, safety_incidents
weather ──> matched by nearest city + hour (there is no key)
```
- Telemetry and reefer readings have **no trip_id**. Join them to trips using `vehicle_id` plus the time between `dispatch_ts` and `arrival_ts`.
- Each trip has 2 delivery_events (Pickup and Delivery).

## A.5 Injected anomalies
| Type | Behavior | Frequency |
|---|---|---|
| EXCESSIVE_IDLING | Engine on while stationary for 45-150 min | ~15% of trips over 100 mi |
| ROUTE_DEVIATION | Truck drifts 6-25 mi off route | ~10% of trips over 150 mi |
| REEFER_UNIT_FAILURE | Refrigeration unit stops for 45-240 min | ~12% of reefer trips |
| COLD_CHAIN_BREACH | Cargo temperature goes above the safe maximum | follows from reefer failures |

## A.6 Data quality to handle in Silver
| Issue | Rate | Fix |
|---|---|---|
| Duplicate batch rows | ~0.3% | De-duplicate on the primary key |
| Duplicate stream events | ~0.4% | De-duplicate on event_id |
| Null foreign keys (trips, fuel_purchases) | ~2% | Flag them or recover from related tables |
| Late events | ~1%, 2-15 min late | Use event_ts plus a watermark |
| Malformed JSON | ~0.02% | Quarantine (dead-letter) |
| Case and whitespace noise | some rows | Trim and standardize case |
| Null GPS, speed, temperature | some rows | Mark as missing, never 0 |
| Repeated daily snapshots | every day | Keep the latest, or model as SCD |

Delivery is **at-least-once**, so consumers must de-duplicate.

## A.7 Cold chain ranges (simulation assumptions, used as a dbt seed)
| Commodity | Setpoint °F | Allowed °F | Share of reefer loads |
|---|---|---|---|
| Pharma | 41 | 36 to 46 | ~10% |
| Chilled | 36 | 33 to 41 | ~45% |
| Frozen | -5 | -10 to 0 | ~45% |

## A.8 KPI index (64 KPIs)
- **Delivery (1-9):** OTD, On-Time Pickup, Avg Delay, Late Rate, Severe Delay, Queue Time, Dock Time, Duration Variance, Distance Variance
- **Cold Chain (10-18):** Observation Compliance, Shipment Compliance, Excursion Count, Duration, Severity, Reefer Failure Rate, Door-Open Exposure, Ambient vs Excursion, Detection Latency
- **Fuel & Cost (19-28):** Fuel Spend, Fuel Cost/Mile, MPG, Price Variance, Idle Fuel, Idle Share, Refuel Behavior, Revenue/Mile, Fuel % of Revenue, Margin Proxy
- **Utilization & Safety (29-40):** Truck Utilization, Miles/Truck/Day, Active Truck Rate, Trailer Utilization, Speeding Rate, Excessive Idling, Route Deviation, Incident Rate, At-Fault/Preventable Share, Claim Cost, Driver Safety Score, Driver Turnover
- **Maintenance (41-47):** Total Cost, Downtime, Frequency, Cost/Mile, Mix, Availability, Cost by Age
- **Weather (48-50):** Duration by Weather, Delay by Weather, Excursion by Ambient Temperature
- **Anomaly Detection (51-53):** Precision, Recall, Time-to-Detect (measured against ground truth)
- **Platform (54-64):** Throughput, E2E Latency, Completeness, Duplicate Rate, Rejection Rate, S3 vs Snowflake Reconciliation, Freshness, Pipeline Success, dbt Test Pass, API Success, Warehouse Cost

## A.9 Dashboards (Power BI)
1. Executive Overview
2. Delivery & Route Performance
3. Cold Chain Monitoring
4. Fuel & Cost
5. Fleet Utilization & Driver Safety
6. Maintenance & Reliability
7. Data Platform Health

Don't import raw telemetry into Power BI. Aggregate it in dbt first.

## A.10 Expected baselines (sanity checks)
| Check | Expected |
|---|---|
| Refrigerated loads | ~50% |
| MPG | 5.8-7.8 |
| Refuel trigger | ~18% tank |
| Maintenance orders | ~8 per truck per year |
| Incidents | ~1.4 per million miles |
| Aggressive trucks | ~8% of fleet |
| Wait between loads | ~60 h on average (so low utilization is by design) |
| Driver turnover | ~15% per year |

## A.11 Known limitations (relationships that don't exist in the simulated data)
- Weather does not affect delays, speed or fuel. It only drives the reefer model.
- Incidents are random per mile driven, so differences between drivers are weak.
- Maintenance is random per truck, so there is no real effect of truck age.
- The data has no road speed limits, no accelerometer, no planned route geometry, no alert timestamps, and no reefer limits in the stream.

## A.12 MVP phases
- **Phase 1:** OTD and On-Time Pickup, Delay and Late Rate, Fuel Spend, MPG, Revenue/Mile, Maintenance Cost and Downtime, Incident Rate and Claims, Cold Chain Compliance and Excursions, Pipeline Success, Reconciliation, Freshness.
- **Phase 2:** Consumption-based fuel cost and Price Variance, Idle, Queue and Dock time, Duration and Distance Variance, Utilization, Speeding and Idling events, Route Deviation, Weather analysis, Anomaly detection Precision and Recall, Margin Proxy.
- **Phase 3:** Predictive models (late deliveries, excursion risk, fuel fraud, maintenance risk) and savings estimates.

## A.13 Notes about the source page
- The parent "Documentation" page is not publicly shared, so its content is not included.
- The Notion share link gives **edit** access to anyone who has it.

---

# Part B: Full Notion Content

- ▸ **Data Catalog**

## 🚛 Fleet Data Platform: Data Catalog
---

## 1. Project Overview

### What is this project?
  A **continuous simulator of a US trucking fleet** (default: 5,000 Class-8 heavy trucks) that runs for days or weeks without stopping and produces **raw data** the same way real source systems would. The data is meant to be the input for a full data engineering pipeline (ingestion, cleaning, modeling, analytics, anomaly detection).

### Why is the data realistic?
  - Trucks follow **Hours-of-Service rules (HOS)**: max 11 hours driving, a 30-minute break after 8 hours, and 10 hours of rest.
  - Trucks **refuel when the tank reaches 18%**, so fuel purchases match fuel consumption.
  - Refrigerated trailers (**reefers**) follow a heat-leak and compressor model driven by **real ambient temperature** from the Open-Meteo weather API.
  - Diesel prices come from the **EIA (US Energy Information Administration)** when an API key is provided, otherwise from a labelled synthetic model.
  - Numeric parameters (mpg, revenue per mile, detention, maintenance cost, incident rate) were calibrated on public datasets.

### Data categories
| Category | What it contains | Format | Destination |
|---|---|---|---|
| **Streaming** | Truck telemetry and reefer (refrigerated trailer) sensors | JSON | Kafka topics, plus 10% of trucks go directly to S3 |
| **Batch** | Business exports: TMS, fuel card, maintenance, safety, registry, HR | CSV.gz | S3 |
| **Reference** | Weather (Open-Meteo), diesel price (EIA) | JSON.gz | S3 |
| **Ground Truth** | Injected anomaly labels, used only to evaluate detection rules | JSONL.gz | S3 |


### Injected anomalies (for anomaly-detection practice)
  1. **EXCESSIVE_IDLING**: truck engine runs 45 to 150 minutes while stationary.
  1. **ROUTE_DEVIATION**: truck drifts 6 to 25 miles off its planned route.
  1. **REEFER_UNIT_FAILURE**: refrigeration unit stops for 45 to 240 minutes.
  1. **COLD_CHAIN_BREACH**: cargo temperature exceeds its safe maximum.

### Intentional data quality problems (dirty on purpose)
  - Null values in IDs, GPS, speed and temperature.
  - Text case and whitespace noise (e.g. `completed`, `COMPLETED`, `Completed `).
  - Duplicate rows and duplicate events (same `event_id`).
  - Late-arriving events (2 to 15 minutes late).
  - Rare malformed JSON messages.

### Reliability features
  - Checkpoint and resume, with catch-up of the gap.
  - Deterministic event IDs, so replays are idempotent.
  - Local disk spool when Kafka is down, and outbox when S3 is down.
  - Graceful shutdown on SIGTERM/SIGINT, and a heartbeat file for Docker health checks.
  - **Delivery guarantee: at-least-once**, so consumers must de-duplicate on `event_id`.
---

## 2. Storage Architecture

### High-level flow
```plain text
                     ┌──────────────────────────────┐
                     │      fleet_generator.py      │
                     │   (vectorised simulation)    │
                     └──────────────┬───────────────┘
        ┌────────────────┬──────────┴───────┬─────────────────┐
        ▼                ▼                  ▼                 ▼
  STREAMING (90%)   STREAMING (10%)      BATCH           REFERENCE + TRUTH
  Kafka topics      Direct to S3      CSV.gz files       JSON.gz / JSONL.gz
        │                │                  │                 │
        └────────────────┴─────────┬────────┴─────────────────┘
                                   ▼
                        Amazon S3 (Bronze / raw layer)
```

### Kafka topics
| Topic | Content | Key | Partitions | Retention |
|---|---|---|---|---|
| `fleet.telemetry.v1` | Truck telemetry (GPS, speed, engine, fuel) | `vehicle_id` | 12 | 48 hours |
| `fleet.reefer.v1` | Refrigerated trailer sensors | `vehicle_id` | 12 | 48 hours |

  Messages are JSON. Older data (backfill older than 24 hours) skips Kafka and goes straight to S3.

### S3 folder layout
  Default root prefix: `fleet/`. All partitions use `dt=YYYY-MM-DD` (date) and `hr=HH` (hour, UTC).
| Layer / Path | Content | File format | Flush interval |
|---|---|---|---|
| `bronze/registry/{trucks,trailers}/dt=/hr=/` | Truck and trailer master data (daily snapshot) | CSV.gz | 15 min |
| `bronze/hr/drivers/dt=/hr=/` | Driver master data (daily snapshot) | CSV.gz | 15 min |
| `bronze/tms/{customers,facilities,routes,loads,trips,delivery_events}/dt=/hr=/` | Transportation Management System exports | CSV.gz | 15 min |
| `bronze/fuel_card/fuel_purchases/dt=/hr=/` | Fuel card transactions | CSV.gz | 15 min |
| `bronze/cmms/maintenance_records/dt=/hr=/` | Maintenance records | CSV.gz | 15 min |
| `bronze/safety/safety_incidents/dt=/hr=/` | Safety incident reports | CSV.gz | 15 min |
| `bronze/prices/diesel_prices/dt=/hr=/` | Daily national diesel price | CSV.gz | 15 min |
| `bronze/stream_direct/{telemetry,reefer}/dt=/hr=/` | Streaming data from "bulk upload" trucks (10% of fleet) and old backfill | JSONL.gz | 10 min |
| `bronze/weather/open_meteo/dt=/` | Raw Open-Meteo API responses | JSON.gz | every fetch (~6 h) |
| `bronze/prices/eia/dt=/` | Raw EIA API responses (only if API key set) | JSON.gz | daily |
| `ground_truth/gen_anomaly_labels/dt=/` | Injected anomaly labels | JSONL.gz | 15 min |

  **File naming:** `{entity}-{run_id}-{sequence}.csv.gz`, where `run_id` identifies each generator run.

### Local state folders (on the machine running the generator)
| Folder | Purpose |
|---|---|
| `state/checkpoint.pkl.gz` | Simulation checkpoint for resume |
| `state/s3_outbox/` | Files waiting to be retried when S3 is unreachable |
| `state/kafka_spool/` | Messages saved when the Kafka broker is down |
| `state/route_cache/` | Cached real road geometry from OSRM (Open Source Routing Machine) |
| `state/heartbeat.json` | Health-check file |
| `logs/fleet.log` | Rotating log file |

---

## 3. Data Catalog
  **Data type notes:** CSV files store everything as text, so the types below are the *logical* types to use when loading. `string` = text, `integer` = whole number, `decimal` = number with fractions, `timestamp` = date and time in UTC (ISO 8601), `boolean` = true/false.
  **Table list**
| # | Table | Source system | Type |
|---|---|---|---|
| 1 | trucks | Registry | Master (daily snapshot) |
| 2 | trailers | Registry | Master (daily snapshot) |
| 3 | drivers | HR (Human Resources) | Master (daily snapshot) |
| 4 | customers | TMS | Master |
| 5 | facilities | TMS | Master |
| 6 | routes | TMS | Master |
| 7 | diesel_prices | Prices | Reference |
| 8 | loads | TMS | Transaction |
| 9 | trips | TMS | Transaction |
| 10 | delivery_events | TMS | Transaction |
| 11 | fuel_purchases | Fuel Card | Transaction |
| 12 | maintenance_records | CMMS | Transaction |
| 13 | safety_incidents | Safety system | Transaction |
| 14 | telemetry (stream) | Truck device | Streaming |
| 15 | reefer (stream) | Trailer sensor | Streaming |
| 16 | gen_anomaly_labels | Generator | Ground truth |

---

### 3.1 trucks
  **Purpose:** The registry of all trucks in the fleet. Each row describes one tractor unit (make, age, tank size, home base) and its current status. A fresh snapshot is written every day, so the same truck appears once per day.
| Column | Data type | Meaning / Description |
|---|---|---|
| truck_id | string | Unique truck identifier, format `TRK00001` |
| unit_number | integer | Fleet unit number painted on the truck |
| make | string | Truck manufacturer (Peterbilt, Freightliner, Mack, Volvo, International, Kenworth) |
| model_year | integer | Year the truck was manufactured |
| vin | string | Vehicle Identification Number (17-character unique chassis ID) |
| acquisition_date | date | Date the company acquired the truck |
| acquisition_mileage | integer | Odometer reading (miles) when the truck was acquired |
| fuel_type | string | Fuel used. Always `Diesel` |
| tank_capacity_gallons | integer | Fuel tank size in US gallons (150, 200 or 250) |
| status | string | `Active` or `Maintenance` at snapshot time |
| home_terminal | string | City of the truck's home terminal |
| snapshot_date | date | Date this snapshot was taken |

---

### 3.2 trailers
  **Purpose:** The registry of all trailers (the cargo box pulled by the truck). Half are refrigerated trailers (reefers) and half are dry vans. Snapshotted daily, and `current_location` shows where the trailer was last dropped.
| Column | Data type | Meaning / Description |
|---|---|---|
| trailer_id | string | Unique trailer identifier, format `TRL00001` |
| trailer_number | integer | Trailer number painted on the unit |
| trailer_type | string | `Refrigerated` or `Dry Van` |
| length_feet | integer | Trailer length in feet (always 53) |
| model_year | integer | Year of manufacture |
| vin | string | Vehicle Identification Number |
| acquisition_date | date | Date the company acquired the trailer |
| status | string | Trailer status (`Active`) |
| current_location | string | City where the trailer currently is |
| snapshot_date | date | Date this snapshot was taken |

---

### 3.3 drivers
  **Purpose:** HR master data for drivers. It tracks hire and termination dates and employment status, and shows driver turnover over time (about 15% per year). All personal data is synthetic. Snapshotted daily.
| Column | Data type | Meaning / Description |
|---|---|---|
| driver_id | string | Unique driver identifier, format `DRV00001` |
| first_name | string | Driver first name |
| last_name | string | Driver last name |
| hire_date | date | Date the driver was hired |
| termination_date | date | Date the driver left the company. Null if still employed |
| license_number | string | Driver license number |
| license_state | string | US state that issued the license |
| date_of_birth | date | Driver date of birth |
| home_terminal | string | City of the driver's home terminal |
| employment_status | string | `Active` or `Terminated` |
| cdl_class | string | Commercial Driver's License (CDL) class. Always `A` (required for heavy combination trucks) |
| years_experience | integer | Years of driving experience |
| snapshot_date | date | Date this snapshot was taken |

---

### 3.4 customers
  **Purpose:** The list of customers (shippers) who book freight. It includes the contract type, payment terms and the kind of freight they usually ship.
| Column | Data type | Meaning / Description |
|---|---|---|
| customer_id | string | Unique customer identifier, format `CUST00001` |
| customer_name | string | Company name (may contain case/space noise) |
| customer_type | string | `Contract` (long-term pricing), `Spot` (one-off) or `Dedicated` (trucks reserved for the customer) |
| credit_terms_days | integer | Days the customer has to pay an invoice (15, 30, 45 or 60) |
| primary_freight_type | string | Main freight category (Automotive, Food/Beverage, Retail, Electronics, Consumer Goods, Industrial) |
| account_status | string | `Active` or `Inactive` |
| contract_start_date | date | Date the customer relationship started |
| annual_revenue_potential | integer | Estimated yearly revenue from this customer (USD) |

---

### 3.5 facilities
  **Purpose:** Physical locations where freight is picked up or delivered (terminals, warehouses, distribution centers). Each facility has GPS coordinates and dock capacity.
| Column | Data type | Meaning / Description |
|---|---|---|
| facility_id | string | Unique facility identifier, format `FAC00001` |
| facility_name | string | Facility name, e.g. "Chicago Terminal" |
| facility_type | string | `Terminal`, `Distribution Center`, `Cross-Dock` or `Warehouse` |
| city | string | City where the facility is located |
| state | string | US state code (2 letters) |
| latitude | decimal | GPS latitude |
| longitude | decimal | GPS longitude |
| dock_doors | integer | Number of loading/unloading dock doors |
| operating_hours | string | Opening hours (`24/7`, `8AM-5PM`, `7AM-7PM`, `6AM-10PM`) |

---

### 3.6 routes
  **Purpose:** The network of lanes (origin to destination city pairs) the fleet drives. Each lane exists in both directions as separate rows. It holds the standard distance, pricing rates and expected transit time.
| Column | Data type | Meaning / Description |
|---|---|---|
| route_id | string | Unique route identifier, format `RTE00001` |
| origin_city | string | Starting city |
| origin_state | string | Starting US state code |
| destination_city | string | Ending city |
| destination_state | string | Ending US state code |
| typical_distance_miles | integer | Standard road distance in miles |
| base_rate_per_mile | decimal | Price charged per mile (USD) |
| fuel_surcharge_rate | decimal | Extra fuel charge per mile (USD) |
| typical_transit_days | integer | Normal number of days to complete the route |

---

### 3.7 diesel_prices
  **Purpose:** The daily national average diesel price used to price fuel purchases. The `source` column tells you whether the value came from the real EIA data or from the built-in model.
| Column | Data type | Meaning / Description |
|---|---|---|
| effective_date | date | Date the price applies to |
| fuel_type | string | Fuel type (`Diesel`) |
| price_per_gallon | decimal | National average price in USD per gallon |
| source | string | `eia` (real data from the US Energy Information Administration) or `model` (synthetic) |

---

### 3.8 loads
  **Purpose:** One row per customer shipment (load) that was completed. It is the **financial** view of a delivery: what was shipped, for whom, on which route, and how much revenue it generated.
| Column | Data type | Meaning / Description |
|---|---|---|
| load_id | string | Unique load identifier, format `LOAD00000001` |
| customer_id | string | Customer who booked the load (links to customers) |
| route_id | string | Route used (links to routes) |
| load_date | date | Date the pickup started |
| load_type | string | `Refrigerated` or `Dry Van` |
| weight_lbs | integer | Cargo weight in pounds |
| pieces | integer | Number of pieces/pallets |
| revenue | decimal | Base freight revenue (USD) |
| fuel_surcharge | decimal | Fuel surcharge revenue (USD) |
| accessorial_charges | integer | Extra fees such as waiting or special handling (USD: 0, 50, 100 or 200) |
| load_status | string | Load status (`Completed`) |
| booking_type | string | `Dedicated`, `Contract` or `Spot` |

---

### 3.9 trips
  **Purpose:** One row per physical trip. It links a load to the driver, truck and trailer that moved it, and records the **operational** result: distance, duration, fuel burned, mpg and idle time. Use it for efficiency and performance analysis.
| Column | Data type | Meaning / Description |
|---|---|---|
| trip_id | string | Unique trip identifier, format `TRIP00000001` |
| load_id | string | Load carried on this trip (links to loads) |
| driver_id | string | Driver who ran the trip (links to drivers). May be null (dirty data) |
| truck_id | string | Truck used (links to trucks). May be null |
| trailer_id | string | Trailer used (links to trailers). May be null |
| dispatch_date | date | Date the trip was dispatched |
| dispatch_ts | timestamp | Actual time pickup started |
| arrival_ts | timestamp | Time the truck arrived at the destination |
| actual_distance_miles | integer | Miles actually driven |
| actual_duration_hours | decimal | Hours from pickup start to arrival |
| fuel_gallons_used | decimal | Gallons of diesel burned during the trip |
| average_mpg | decimal | Miles per gallon (mpg) achieved |
| idle_time_hours | decimal | Hours the engine ran while the truck was not driving |
| trip_status | string | Trip status (`Completed`) |

---

### 3.10 delivery_events
  **Purpose:** Records the two key moments of each trip, the **Pickup** and the **Delivery**. Each trip creates two rows. It compares scheduled and actual times, so it is the main table for on-time performance and detention analysis.
| Column | Data type | Meaning / Description |
|---|---|---|
| event_id | string | Unique event identifier, format `EVT00000001` |
| load_id | string | Related load (links to loads) |
| trip_id | string | Related trip (links to trips) |
| event_type | string | `Pickup` or `Delivery` |
| facility_id | string | Facility where the event happened (links to facilities) |
| scheduled_datetime | timestamp | Planned time of the event |
| actual_datetime | timestamp | Actual time the event started |
| detention_minutes | integer | Minutes spent at the dock loading/unloading (detention = time a truck is held at a facility) |
| on_time_flag | boolean | True if the event started within a 15-minute grace period of schedule |
| location_city | string | City of the event |
| location_state | string | US state code of the event |

---

### 3.11 fuel_purchases
  **Purpose:** Fuel card transactions. A purchase is generated whenever a truck's tank falls below 18%. Use it for fuel cost analysis, price comparison by state, and reconciling purchases against consumption.
| Column | Data type | Meaning / Description |
|---|---|---|
| fuel_purchase_id | string | Unique purchase identifier, format `FUEL000000001` |
| trip_id | string | Trip during which fuel was bought (links to trips) |
| truck_id | string | Truck that was refueled (links to trucks). May be null |
| driver_id | string | Driver who made the purchase (links to drivers). May be null |
| purchase_date | timestamp | Date and time of the purchase |
| location_city | string | City of the fuel stop |
| location_state | string | US state code of the fuel stop |
| gallons | decimal | Gallons purchased |
| price_per_gallon | decimal | Price paid per gallon (USD) |
| total_cost | decimal | Total cost (gallons × price, USD) |
| fuel_card_number | string | Fuel card identifier used for payment |

---

### 3.12 maintenance_records
  **Purpose:** Repair and service history of each truck from the CMMS (Computerized Maintenance Management System). It shows cost, labor and downtime, and is used for maintenance cost and truck availability analysis.
| Column | Data type | Meaning / Description |
|---|---|---|
| maintenance_id | string | Unique maintenance job identifier, format `MAINT00000001` |
| truck_id | string | Truck that was serviced (links to trucks) |
| maintenance_date | date | Date the service started |
| maintenance_type | string | Inspection, Repair, Preventive, Engine, Tire, Transmission or Brake |
| odometer_reading | integer | Truck odometer (miles) at service time |
| labor_hours | decimal | Hours of mechanic labor |
| labor_cost | decimal | Labor cost (USD) |
| parts_cost | decimal | Cost of parts (USD) |
| total_cost | decimal | Labor + parts cost (USD) |
| facility_location | string | City of the repair shop |
| downtime_hours | decimal | Hours the truck was out of service |
| service_description | string | Short text, e.g. "Scheduled Brake" or "Emergency Engine" |

---

### 3.13 safety_incidents
  **Purpose:** Safety events such as accidents, violations and complaints. It includes fault, injury, preventability and the cost of damage. Use it for driver safety scoring and claims analysis.
| Column | Data type | Meaning / Description |
|---|---|---|
| incident_id | string | Unique incident identifier, format `INC00000001` |
| trip_id | string | Trip during which it happened (links to trips) |
| truck_id | string | Truck involved (links to trucks) |
| driver_id | string | Driver involved (links to drivers) |
| incident_date | timestamp | Date and time of the incident |
| incident_type | string | DOT Violation, Equipment Damage, Accident, Customer Complaint or Moving Violation (DOT = US Department of Transportation) |
| location_city | string | City where it happened |
| location_state | string | US state code |
| at_fault_flag | boolean | True if the driver/company was at fault |
| injury_flag | boolean | True if anyone was injured |
| vehicle_damage_cost | decimal | Cost of damage to the vehicle (USD) |
| cargo_damage_cost | decimal | Cost of damage to the cargo (USD) |
| claim_amount | decimal | Total claim = vehicle damage + cargo damage + fines (USD) |
| preventable_flag | boolean | True if the incident could have been avoided |
| description | string | Short text: severity and cause (weather, traffic, equipment, other driver, road conditions) |

---

### 3.14 telemetry (streaming)
  **Purpose:** Real-time signals sent by the GPS and engine device (telematics unit) on each truck. A message is sent every tick (1 minute by default) while the engine is on, and 5× less often when parked. It is the base for live tracking, idling detection and route deviation detection.
  **Location:** Kafka topic `fleet.telemetry.v1` or `bronze/stream_direct/telemetry/` (JSON Lines)
| Column | Data type | Meaning / Description |
|---|---|---|
| schema_version | integer | Version of the message format (currently 1) |
| event_id | string | Deterministic unique ID (e.g. `T00001<epoch>`). Use it to de-duplicate |
| vehicle_id | string | Truck ID (same as `trucks.truck_id`) |
| device_id | string | Telematics device ID, format `TU-00001` (TU = Telematics Unit) |
| event_ts | timestamp | Time the reading was taken on the device |
| source_sequence | integer | Per-truck counter that increases with each message (detects gaps and order) |
| lat | decimal | GPS latitude. Null when GPS signal is lost |
| lon | decimal | GPS longitude. Null when GPS signal is lost |
| speed_mph | decimal | Speed in miles per hour. Null if sensor fails |
| heading_deg | integer | Direction of travel in degrees (0 = North) |
| rpm | integer | Engine speed in revolutions per minute (RPM) |
| engine_temp_f | decimal | Engine temperature in degrees Fahrenheit |
| fuel_gph | decimal | Current fuel burn rate in gallons per hour |
| fuel_level_gal | decimal | Fuel remaining in the tank (gallons) |
| odometer_mi | decimal | Total distance on the odometer (miles) |
| engine_on | boolean | True if the engine is running |
| ingest_ts | timestamp | Time the message reached the platform (can be later than `event_ts`) |

---

### 3.15 reefer (streaming)
  **Purpose:** Sensor readings from refrigerated trailers (reefers) that carry temperature-sensitive cargo (pharma, chilled, frozen). It tracks cargo temperature against the target to catch refrigeration failures and cold-chain breaches.
  **Location:** Kafka topic `fleet.reefer.v1` or `bronze/stream_direct/reefer/` (JSON Lines)
| Column | Data type | Meaning / Description |
|---|---|---|
| schema_version | integer | Version of the message format (currently 1) |
| event_id | string | Deterministic unique ID (e.g. `R00001<epoch>`). Use it to de-duplicate |
| vehicle_id | string | Truck pulling the trailer |
| trailer_id | string | Refrigerated trailer ID (same as `trailers.trailer_id`) |
| sensor_id | string | Temperature sensor ID, format `RF-TRL00001-S1` |
| event_ts | timestamp | Time the reading was taken |
| source_sequence | integer | Per-truck message counter |
| cargo_temp_f | decimal | Cargo temperature in °F. Null if the sensor drops a reading |
| setpoint_f | decimal | Target temperature in °F (Pharma ≈ 41, Chilled ≈ 36, Frozen ≈ -5) |
| compressor_on | boolean | True if the cooling compressor is running |
| door_open | boolean | True if the trailer door is open (during loading/unloading) |
| ambient_temp_f | decimal | Outside air temperature in °F |
| reefer_fuel_gph | decimal | Fuel burn of the refrigeration unit (gallons per hour) |
| unit_mode | string | Operating mode of the unit (`CONTINUOUS`) |
| ingest_ts | timestamp | Time the message reached the platform |

---

### 3.16 gen_anomaly_labels (ground truth)
  **Purpose:** The answer key. It lists every anomaly the generator injected, with exact start and end times. Use it **only to measure how well your detection rules perform**. Never use it inside the rules themselves.
  **Location:** `ground_truth/gen_anomaly_labels/` (JSON Lines)
| Column | Data type | Meaning / Description |
|---|---|---|
| anomaly_id | string | Unique anomaly identifier, format `A00000001` |
| anomaly_type | string | `EXCESSIVE_IDLING`, `ROUTE_DEVIATION`, `REEFER_UNIT_FAILURE` or `COLD_CHAIN_BREACH` |
| vehicle_id | string | Truck affected |
| trip_id | string | Trip during which the anomaly happened |
| start_ts | timestamp | When the anomaly started |
| end_ts | timestamp | When the anomaly ended |
| params | string (JSON) | Extra details by type, e.g. `duration_min`, `max_offset_miles`, `peak_temp_f`, `cause` |

---

## 4. Relationships Summary
| From (child) | Column | To (parent) | Column |
|---|---|---|---|
| loads | customer_id | customers | customer_id |
| loads | route_id | routes | route_id |
| trips | load_id | loads | load_id |
| trips | driver_id | drivers | driver_id |
| trips | truck_id | trucks | truck_id |
| trips | trailer_id | trailers | trailer_id |
| delivery_events | load_id | loads | load_id |
| delivery_events | trip_id | trips | trip_id |
| delivery_events | facility_id | facilities | facility_id |
| fuel_purchases | trip_id / truck_id / driver_id | trips / trucks / drivers | trip_id / truck_id / driver_id |
| maintenance_records | truck_id | trucks | truck_id |
| safety_incidents | trip_id / truck_id / driver_id | trips / trucks / drivers | trip_id / truck_id / driver_id |
| telemetry, reefer | vehicle_id | trucks | truck_id |
| reefer | trailer_id | trailers | trailer_id |
| gen_anomaly_labels | vehicle_id / trip_id | trucks / trips | truck_id / trip_id |

---

## 5. Data Quality Notes (what to clean in Silver layer)
| Issue | Where | How to handle |
|---|---|---|
| Duplicate rows (~0.3%) | trips, loads, delivery_events, fuel_purchases, safety_incidents | De-duplicate on the primary key |
| Duplicate stream events (~0.4%) | telemetry, reefer | De-duplicate on `event_id` |
| Null foreign keys (~2%) | trips (driver/truck/trailer), fuel_purchases (driver/truck) | Flag or recover from related tables |
| Case and whitespace noise | customer_name, load_status, booking_type, trip_status, location_city, facility_location | Trim and standardize case |
| Null GPS / speed / temperature | telemetry, reefer | Keep the row, mark value as missing |
| Late-arriving events | telemetry, reefer | Use `event_ts` (not `ingest_ts`) for event time and allow a watermark |
| Malformed JSON (~0.02%) | telemetry, reefer | Send to a dead-letter / quarantine path |
| Repeated daily snapshots | trucks, trailers, drivers, customers, facilities, routes | Keep latest, or model as SCD (Slowly Changing Dimension) |

---

## 6. Glossary of Abbreviations
| Term | Meaning |
|---|---|
| TMS | Transportation Management System |
| CMMS | Computerized Maintenance Management System |
| HR | Human Resources |
| HOS | Hours of Service (legal limits on driving time) |
| Reefer | Refrigerated trailer |
| Dry Van | Standard enclosed non-refrigerated trailer |
| VIN | Vehicle Identification Number |
| CDL | Commercial Driver's License |
| DOT | US Department of Transportation |
| EIA | US Energy Information Administration |
| OSRM | Open Source Routing Machine |
| MPG | Miles Per Gallon |
| GPH | Gallons Per Hour |
| RPM | Revolutions Per Minute |
| GPS | Global Positioning System |
| Detention | Time a truck waits or is held at a facility |
| Accessorial charges | Extra fees on top of the base freight price |
| Fuel surcharge | Extra charge that follows the fuel price |
| Bronze layer | Raw, unprocessed data exactly as received |
| SCD | Slowly Changing Dimension |
| UTC | Coordinated Universal Time |

- ▸ **KPIs**

## 🚛 Fleet Data Platform: Business Questions, KPI Framework & Analytics Requirements
  **Project Focus:** Delivery Performance, Cold Chain Compliance, Fuel Efficiency, Fleet Utilization, Maintenance, Safety, and Data Platform Health
  **Units used in this project:** miles (mi), miles per hour (mph), gallons (gal), US dollars (USD), degrees Fahrenheit (°F). All timestamps are in UTC.
---

## 1. Project Objective
  This platform helps a US trucking company monitor fleet operations, improve delivery reliability, protect temperature-sensitive cargo, control fuel and maintenance costs, and make data-driven decisions.
  The data comes from a simulated fleet (default 5,000 Class-8 trucks) that behaves like real source systems:
  - **Truck telemetry** (GPS, speed, engine, fuel level, odometer) as JSON streams.
  - **Reefer sensors** (refrigerated trailer cargo temperature, compressor, door) as JSON streams.
  - **TMS exports** (Transportation Management System): customers, facilities, routes, loads, trips, delivery events.
  - **Fuel card** purchases and **diesel reference prices** (EIA, Energy Information Administration, or a labelled model).
  - **CMMS** maintenance records (Computerized Maintenance Management System).
  - **Safety** incident reports.
  - **Registry and HR** master data: trucks, trailers, drivers.
  - **Weather** from Open-Meteo.
  - **Ground truth** anomaly labels (used only to evaluate detection, never inside the detection rules).
  The platform should not only report what happened. It should explain why performance changed, flag operational risks, and give evidence for the next decision.

### Primary business outcomes
  1. Improve on-time pickup and delivery performance.
  1. Reduce cold-chain temperature violations and cargo-loss risk.
  1. Reduce fuel consumption and cost per mile.
  1. Improve truck and driver utilization.
  1. Reduce unplanned maintenance and downtime.
  1. Detect route deviations, excessive idling, speeding, and refrigeration failures.
  1. Provide reliable, timely, and traceable data for decisions.
---

## 2. Business Questions We Must Answer
  KPIs and dashboards are designed around these questions.

### A. Delivery Performance & Customer Service
  **Q1. Are we picking up and delivering on time?**
  - What percentage of pickups and deliveries start within the allowed window?
  - What is the average and median delay?
  - How many deliveries are severely late?
  **Q2. Why are deliveries late?**
  - Is the delay created before departure (waiting for pickup or loading) or during the trip?
  - How much time is lost in the queue at the destination before unloading starts?
  - Which routes, origin/destination cities, days, or hours have the worst performance?
  **Q3. Which customers and lanes receive the worst service?**
  - Which customers and booking types (Contract, Spot, Dedicated) have the lowest on-time rate?
  - Which lanes (origin to destination) are consistently late?
  **Q4. Are routes performing as planned?**
  - Planned vs actual trip duration and distance.
  - Which routes have the largest overruns?
  - Do trucks leave their route?
  **Business decisions enabled:** Better dispatch planning, more realistic delivery promises, customer service priorities, and lane review.

### B. Cold Chain & Cargo Safety
  **Q5. Are refrigerated loads kept within the safe temperature range?**
  - What share of refrigerated loads had no temperature excursion?
  - How many excursions happened, how long did they last, and how severe were they?
  **Q6. Which trucks, trailers, routes, and conditions carry the highest cold-chain risk?**
  - Which trailers fail repeatedly?
  - Are excursions linked to refrigeration unit failures, door openings, or high ambient temperature?
  **Q7. How fast can we detect an excursion?**
  - How long between the first out-of-range reading and the moment the data is available?
  - Which excursions never returned to range?
  **Business decisions enabled:** Equipment inspection, dock/door procedures, priority handling of high-risk loads, claims prevention.

### C. Fuel Efficiency & Operating Cost
  **Q8. What does it cost to run the fleet?**
  - Total fuel spend, fuel cost per mile, fuel cost per trip.
  - Maintenance cost and its share of revenue.
  **Q9. Which trucks and routes are the least fuel-efficient?**
  - Miles per gallon (MPG) by truck, route, and driver.
  - How much fuel is burned while idling?
  **Q10. Are fuel purchases consistent with expected prices and usage?**
  - Is the price paid higher than the reference price?
  - Are there unusually large or unusually small purchases?
  **Q11. Are we profitable per mile?**
  - Revenue per mile, and fuel cost as a percentage of revenue.
  **Business decisions enabled:** Route and driving-behavior optimization, fuel-stop policy, truck allocation, pricing review.

### D. Fleet Utilization & Driver Safety
  **Q12. Are we using the fleet efficiently?**
  - How much time do trucks spend driving, idling, waiting, loading, and in maintenance?
  - Which trucks are underutilized?
  **Q13. Which driving behaviors create risk?**
  - How often do trucks exceed a defined speed threshold?
  - Which trucks or drivers show repeated speeding or excessive idling?
  **Q14. How frequent and costly are safety incidents?**
  - Incidents per million miles, at-fault share, preventable share, claim cost.
  **Business decisions enabled:** Driver coaching, truck assignment, safety program priorities.

### E. Maintenance & Asset Reliability
  **Q15. Are trucks going out of service too often?**
  - How many maintenance orders, at what cost, and how many hours of downtime?
  - Which trucks have repeated orders?
  **Q16. Can telemetry give early warning?**
  - Do abnormal engine temperatures appear before maintenance events?
  **Business decisions enabled:** Preventive maintenance planning and availability management.

### F. Weather & External Conditions
  **Q17. How does weather affect the operation?**
  - Are refrigeration breaches more frequent at high ambient temperatures?
  - Are delays, speed, or fuel consumption different in rain, wind, or heat?
  **Important:** Correlation is not causation. Control for route, distance, and time of day before claiming that weather caused a change. See Section 8 for what the simulator actually models.
---

## 3. KPI Framework
  Each KPI has a definition, formula, unit, source, dimensions, and business action. Formulas are proposals, not measured results.

### A. Delivery Performance KPIs

#### KPI 1: On-Time Delivery Rate (OTD)
  **Business question:** What percentage of deliveries started unloading within the allowed window?
  **Formula:**
OTD (%) = (Delivery events with on_time_flag = true / Total eligible Delivery events) × 100
  **Required data:** `delivery_events.event_type`, `delivery_events.on_time_flag`, `delivery_events.scheduled_datetime`, `delivery_events.actual_datetime`
  **Dimensions:** Date, customer, route, origin/destination city, booking type, load type (Refrigerated or Dry Van), truck.
  **Note:** `on_time_flag` already uses a 15-minute grace period. Keep this rule consistent across all reports.
  **Business action:** Investigate low-performing lanes and customers.

#### KPI 2: On-Time Pickup Rate
  **Formula:**
On-Time Pickup (%) = (Pickup events with on_time_flag = true / Total eligible Pickup events) × 100
  **Business action:** Find loading and dispatch delays that start the trip late.

#### KPI 3: Average Delivery Delay
  **Formula:**
Delay (minutes) = actual_datetime − scheduled_datetime (Delivery events only)
Average Delay = Sum of positive delays / Number of eligible Delivery events
Report early deliveries (negative delay) separately so they do not cancel out late ones. Also report median and p90.
  **Business action:** Prioritize recurring delays.

#### KPI 4: Late Delivery Rate
  **Formula:**
Late Delivery Rate (%) = (Deliveries with delay > grace period / Total eligible deliveries) × 100
  **Relationship:** Approximately 100% minus OTD under the same rules.

#### KPI 5: Severe Delay Rate
  **Formula:**
Severe Delay Rate (%) = (Deliveries delayed beyond a threshold / Total eligible deliveries) × 100
  **Required decision:** The team must pick the threshold (for example 60 or 120 minutes) and label it as an assumption.

#### KPI 6: Destination Queue Time
  **Definition:** Time a truck waits at the destination before unloading starts.
**Formula:**
Queue Time (minutes) = Delivery `actual_datetime` − `trips.arrival_ts`
  **Business action:** Identify facilities and cities with long waiting times (a major source of lost driver hours).

#### KPI 7: Dock Time (Detention Minutes)
  **Definition:** Time spent loading or unloading at the dock.
**Formula:**
Average Dock Time = Average of `delivery_events.detention_minutes`, split by Pickup and Delivery.
  **Business action:** Review slow facilities and negotiate detention fees.
**Note:** In this dataset, `detention_minutes` is the dock handling time, not only the time beyond a free period.

#### KPI 8: Trip Duration Variance
  **Formula:**
Planned Duration (hours) = scheduled delivery time − scheduled pickup time
Actual Duration (hours) = `trips.actual_duration_hours`
Variance (%) = ((Actual − Planned) / Planned) × 100
  **Business action:** Review inaccurate time estimates and lanes with recurring overruns.
**Caution:** Planned duration includes the slack factor built into the schedule, so compare lanes with each other rather than reading the absolute value alone.

#### KPI 9: Distance Variance
  **Formula:**
Distance Variance (%) = ((`trips.actual_distance_miles` − `routes.typical_distance_miles`) / `routes.typical_distance_miles`) × 100
  **Business action:** Investigate detours and inaccurate lane distances.
**Caution:** Actual distance comes from the simulated truck movement. Define one authoritative distance source (trip distance vs odometer difference) and use it everywhere.
---

### B. Cold Chain KPIs
  **Important design note:** The reefer stream contains `cargo_temp_f` and `setpoint_f`, but **not** the allowed minimum and maximum. The simulator uses commodity classes with these setpoints and limits, and they are **simulation assumptions, not regulatory values**:
| Commodity | Setpoint (°F) | Allowed range (°F) |
|---|---|---|
| Pharma | 41 | 36 to 46 |
| Chilled | 36 | 33 to 41 |
| Frozen | -5 | -10 to 0 |

  The team must create a small reference table (for example a dbt seed) that maps `setpoint_f` to its allowed range, and document it as an assumption.

#### KPI 10: Cold Chain Compliance Rate (observation level)
  **Formula:**
Compliant Observation Rate (%) = (Valid readings within the allowed range / Total valid readings) × 100
  **Required data:** `reefer.cargo_temp_f`, `reefer.setpoint_f`, the commodity range seed table.
**Rule:** Readings with null `cargo_temp_f` are excluded and counted separately. Never treat null as 0.
**Note:** This measures readings, not loads.

#### KPI 11: Shipment-Level Cold Chain Compliance
  **Formula:**
Shipment Compliance (%) = (Refrigerated loads with no confirmed excursion / Total refrigerated loads) × 100
  **Required data:** Reefer readings joined to trips by `vehicle_id` (and `trailer_id`) and the time window `trips.dispatch_ts` to `trips.arrival_ts`. Only loads where `loads.load_type = 'Refrigerated'` are eligible.
**Definition:** A load is compliant only if its monitoring window has no confirmed excursion.

#### KPI 12: Temperature Excursion Count
  **Definition:** Number of distinct events where cargo temperature leaves the allowed range.
**Event logic:**
  - Start when a reading goes outside the range.
  - Continue while it stays outside.
  - Close when it returns, or when the trip ends.
  - Use a minimum duration or a number of consecutive readings (for example 2 readings) to avoid sensor noise creating false events (the sensor adds small random noise).

#### KPI 13: Excursion Duration
  **Formula:**
Excursion Duration (minutes) = Event End − Event Start
Report total, average, median, and maximum.

#### KPI 14: Excursion Severity
  **Formula:**
Above range: Severity (°F) = Measured temperature − Maximum allowed
Below range: Severity (°F) = Minimum allowed − Measured temperature
Report the peak severity and duration separately.

#### KPI 15: Refrigeration Failure Rate
  **Definition:** Share of refrigerated trips where the compressor stops for a long period.
**Detection rule (proposed):** `compressor_on = false` for a continuous period longer than a defined threshold while `cargo_temp_f` is above the setpoint plus the deadband.
**Business action:** Identify trailers needing inspection.

#### KPI 16: Door-Open Exposure
  **Formula:**
Door-Open Minutes per Refrigerated Trip = Count of readings with `door_open = true` × reading interval
**Business action:** Reduce door-open time during loading and unloading.

#### KPI 17: Ambient Temperature vs Excursion Rate
  **Definition:** Excursion rate grouped by `ambient_temp_f` bands (for example below 50, 50 to 70, 70 to 90, above 90 °F).
**Business action:** Prepare for high-risk heat periods.

#### KPI 18: Excursion Detection Latency (data latency version)
  **Formula:**
Detection Latency = Timestamp when the excursion is first visible in Snowflake − First out-of-range `event_ts`
  **Important:** The source has no alert system. Until a detection job and an alert timestamp exist, this KPI is a **data-availability latency**, not a real alert latency. Do not mix the two.
---

### C. Fuel & Cost KPIs

#### KPI 19: Total Recorded Fuel Expenditure
  **Formula:**
Total Fuel Spend (USD) = Sum of `fuel_purchases.total_cost`
  **Dimensions:** Date, truck, driver, state, city.
**Caution:** This is purchased fuel, not fuel consumed in the same period.

#### KPI 20: Fuel Cost per Mile
  **Formula:**
Fuel Cost per Mile (USD/mi) = Fuel cost of completed trips / Miles of completed trips
**Recommended method:** Use `trips.fuel_gallons_used` × the purchase price for the same period for a consumption-based version, and compare it with the purchase-based version. Document which one is authoritative.

#### KPI 21: Fuel Efficiency (MPG)
  **Formula:**
MPG = `trips.actual_distance_miles` / `trips.fuel_gallons_used` (or the stored `average_mpg`)
**Dimensions:** Truck, route, driver, make, tank size.
**Business action:** Find trucks and routes that burn more fuel than similar ones.

#### KPI 22: Fuel Price Variance
  **Formula:**
Price Variance (%) = ((`fuel_purchases.price_per_gallon` − `diesel_prices.price_per_gallon`) / `diesel_prices.price_per_gallon`) × 100
**Caution:** `diesel_prices` is a national price and the simulator adds a **state offset** (for example California is much higher than Texas). So compare within the same state, or compute the expected state price, before flagging outliers.

#### KPI 23: Idle Fuel Consumption
  **Definition:** Fuel burned while the engine is on and the truck is not moving.
**Formula:**
Idle Fuel (gal) = Sum of `telemetry.fuel_gph` × time interval, where `engine_on = true` and `speed_mph` is about 0
**Alternative (trip level):** `trips.idle_time_hours`.
**Caution:** Zero speed alone is not idling. Always check `engine_on`.

#### KPI 24: Idle Time Share
  **Formula:**
Idle Share (%) = `trips.idle_time_hours` / `trips.actual_duration_hours` × 100

#### KPI 25: Refuel Behavior
  **Definition:** Average gallons per refuel, and tank level at purchase.
**Formula:**
Fuel Level at Refuel = Latest `telemetry.fuel_level_gal` before the purchase / `trucks.tank_capacity_gallons`
  **Business action:** Check that refueling policy is followed. The simulator refuels at about 18% tank level, so large deviations point to data or matching problems.

#### KPI 26: Revenue per Mile
  **Formula:**
Revenue per Mile (USD/mi) = (`loads.revenue` + `loads.fuel_surcharge` + `loads.accessorial_charges`) / `trips.actual_distance_miles`
  **Dimensions:** Customer, booking type, route, load type.

#### KPI 27: Fuel Cost as % of Revenue
  **Formula:**
Fuel Cost % = Fuel cost of the trip / Total load revenue × 100

#### KPI 28: Operating Margin Proxy per Trip
  **Formula:**
Margin Proxy (USD) = Total load revenue − Fuel cost − Allocated maintenance cost
**Caution:** This is a **proxy**. It excludes driver pay, insurance, depreciation, and tolls. Do not present it as profit.
---

### D. Fleet Utilization & Driver Safety KPIs

#### KPI 29: Truck Utilization Rate (time based)
  **Formula:**
Utilization (%) = Time in driving, loading, unloading (productive states) / Total available time × 100
**Required data:** `telemetry.engine_on`, `telemetry.speed_mph`, and trip timestamps.
**Definition rule:** Agree whether utilization means time, distance, or load-capacity utilization. These are different measures.
**Note:** The simulator is configured so that trucks wait a long time between loads (average idle gap between loads is set to 60 hours). Low utilization is therefore **expected from the configuration**, so use this KPI to compare trucks with each other, not to judge the absolute level.

#### KPI 30: Miles per Truck per Day
  **Formula:**
Miles per Truck per Day = Sum of `trips.actual_distance_miles` / (Number of trucks × days in period)

#### KPI 31: Active Truck Rate
  **Formula:**
Active Truck Rate (%) = Trucks with at least one trip or driving event in the period / Eligible trucks × 100
**Definition rule:** Decide if trucks under maintenance are included in the denominator.

#### KPI 32: Trailer Utilization
  **Formula:**
Trailer Utilization (%) = Trailer time attached to a trip / Total time. Use `trips.trailer_id`.
**Business action:** Right-size the trailer pool. The fleet has more trailers than trucks.

#### KPI 33: Speeding Event Rate
  **Formula:**
Speeding Events per 100 Miles = (Validated speeding events / Miles traveled) × 100
  **Speeding rule (proposed, must be labelled as an assumption):** `speed_mph` above a fixed threshold (for example 70 mph) for at least N consecutive readings.
**Caution:** The data has **no road speed-limit information**, so this is a fixed-threshold KPI, not a legal speeding measure. Null `speed_mph` readings must be excluded, not treated as 0.

#### KPI 34: Excessive Idling Events
  **Definition:** Continuous periods where `engine_on = true` and speed is about 0 for longer than a threshold (for example 30 minutes) outside normal loading and unloading.
**Business action:** Coaching and idle-reduction policy.
**Evaluation:** Compare detected events with the `EXCESSIVE_IDLING` rows in `gen_anomaly_labels`.

#### KPI 35: Route Deviation Rate
  **Formula:**
Route Deviation Rate (%) = (Trips with at least one confirmed deviation / Total eligible trips) × 100
  **Method (proposed):** Distance from each GPS point to the straight line between the origin and destination facilities (`facilities.latitude/longitude`) above a threshold (for example 5 miles).
**Caution:** This works well when the generator uses great-circle route geometry. If real OSRM road geometry is used (`fetch-routes`), normal roads curve away from the straight line, so the threshold must be re-tuned or a real route geometry must be stored.
**Evaluation:** Compare with `ROUTE_DEVIATION` labels.

#### KPI 36: Safety Incident Rate
  **Formula:**
Incidents per Million Miles = (Count of `safety_incidents` / Miles traveled) × 1,000,000
**Dimensions:** Incident type, state, truck, driver.

#### KPI 37: At-Fault and Preventable Incident Share
  **Formula:**
At-Fault Share (%) = Incidents with `at_fault_flag = true` / Total incidents × 100
Preventable Share (%) = Incidents with `preventable_flag = true` / Total incidents × 100

#### KPI 38: Claim Cost
  **Formula:**
Total Claim Amount (USD) = Sum of `safety_incidents.claim_amount`
Claim Cost per Million Miles = Total claims / Miles × 1,000,000

#### KPI 39: Driver Safety Score
  **Purpose:** A single indicator for coaching.
**Potential inputs:** Speeding events per 100 miles, excessive idling events, incidents per million miles.
**Rule:** Build it only after the event definitions are agreed, normalize by miles driven, and do not publish an arbitrary score as an objective measure of driver quality.

#### KPI 40: Driver Turnover Rate
  **Formula:**
Turnover (%) = Drivers with `employment_status = 'Terminated'` in the period / Average active drivers × 100
**Required data:** `drivers.termination_date`, `drivers.employment_status` (use the latest daily snapshot per driver).
---

### E. Maintenance & Reliability KPIs

#### KPI 41: Total Maintenance Cost
  **Formula:**
Total Maintenance Cost (USD) = Sum of `maintenance_records.total_cost`
Split into labor (`labor_cost`) and parts (`parts_cost`).

#### KPI 42: Maintenance Downtime
  **Formula:**
Total Downtime (hours) = Sum of `maintenance_records.downtime_hours`
Average Downtime per Order = Total downtime / Number of orders
**Note:** This dataset gives downtime directly and does not give open and close timestamps.

#### KPI 43: Maintenance Frequency
  **Formula:**
Orders per Truck = Count of `maintenance_records` per `truck_id` in the period
Also report orders per 10,000 miles, using odometer or trip miles.

#### KPI 44: Maintenance Cost per Mile
  **Formula:**
Maintenance Cost per Mile = Maintenance cost in the period / Miles traveled in the same period
**Caution:** Use a long enough window (monthly or quarterly) because maintenance events are infrequent.

#### KPI 45: Maintenance Mix
  **Definition:** Cost and count by `maintenance_type` (Inspection, Repair, Preventive, Engine, Tire, Transmission, Brake).
**Business action:** Find the categories that drive cost.

#### KPI 46: Truck Availability Rate
  **Formula:**
Availability (%) = Time not in maintenance / Total fleet time × 100
**Required data:** `maintenance_records.downtime_hours` or `trucks.status` in the daily snapshots.

#### KPI 47: Cost per Odometer Mile (age effect)
  **Definition:** Maintenance cost grouped by truck age (`trucks.model_year`) or odometer band.
**Caution:** The simulator assigns maintenance randomly across trucks, so do not expect strong age effects.
---

### F. Weather & Context KPIs

#### KPI 48: Average Trip Duration by Weather Condition
  **Required data:** Trips, telemetry location, Open-Meteo observations (temperature, humidity, precipitation, wind speed, weather code).
**Caution:** Telemetry does not carry a city. Match each reading to the nearest weather city by latitude and longitude, and use the hour that matches `event_ts`.

#### KPI 49: Delivery Delay by Weather Condition
  **Definition:** Average delay and OTD grouped by weather bands at origin, destination, or along the route.
**Caution:** See Section 8 before drawing conclusions.

#### KPI 50: Excursion Rate by Ambient Temperature
  **Definition:** Same as KPI 17, using the Open-Meteo observation or the `reefer.ambient_temp_f` value.
**Note:** This is the one weather relationship the simulator **does** model: ambient temperature drives the reefer heat leak and compressor capacity.
---

### G. Anomaly Detection Quality KPIs (unique to this project)
  The generator injects four anomaly types and logs them in `ground_truth/gen_anomaly_labels`: `EXCESSIVE_IDLING`, `ROUTE_DEVIATION`, `REEFER_UNIT_FAILURE`, `COLD_CHAIN_BREACH`.

#### KPI 51: Detection Precision
  Precision (%) = Correctly detected anomalies / All anomalies flagged by our rules × 100

#### KPI 52: Detection Recall
  Recall (%) = Correctly detected anomalies / All injected anomalies in the labels × 100

#### KPI 53: Time-to-Detect (against truth)
  Delay (minutes) = Our detection timestamp − label `start_ts`
  **Rules:**
  - A detection counts as correct if it matches the same `vehicle_id` and overlaps the label's `start_ts` to `end_ts` window.
  - Labels are used **only for evaluation**, never inside the detection rules.
  - Report each metric per anomaly type.
---

## 4. Data Platform & Pipeline KPIs
  Business KPIs show how the fleet performs. These show whether the data behind them is trustworthy and timely.

#### KPI 54: Event Ingestion Throughput
  Events per minute that land in S3 and Snowflake (telemetry and reefer separately). Track from file counts and row counts.

#### KPI 55: End-to-End Data Latency
  **Formula:**
Latency = Time the row is available in Snowflake − `event_ts`
Report median, p95, and p99.
**Also report:** Source latency = `ingest_ts` − `event_ts` (the generator delays about 1% of messages by 2 to 15 minutes to simulate late data).

#### KPI 56: Data Completeness Rate
  **Formula:**
Completeness (%) = Non-null values in required fields / Expected values × 100
**Fields to monitor:** `trips.driver_id/truck_id/trailer_id`, `fuel_purchases.driver_id/truck_id`, `telemetry.lat/lon/speed_mph`, `reefer.cargo_temp_f`.

#### KPI 57: Duplicate Rate
  **Formula:**
Duplicate Rate (%) = Duplicate records / Total received records × 100
**Keys:** Batch tables use the primary key (`trip_id`, `load_id`, `event_id`, `fuel_purchase_id`, `incident_id`). Streams use `event_id`.

#### KPI 58: Rejection (Quarantine) Rate
  **Formula:**
Rejection Rate (%) = Rejected or quarantined records / Total received records × 100
**Source:** Malformed JSON messages (truncated payloads, renamed `event_ts` field).

#### KPI 59: Row Count Reconciliation (S3 vs Snowflake)
  **Formula:**
Reconciliation Gap (%) = |Rows in S3 files − Rows in Snowflake RAW| / Rows in S3 files × 100
**Purpose:** Prove that Airbyte moved everything. Run per table and per day.

#### KPI 60: Data Freshness
  **Definition:** Time since the latest valid record became available in each layer (S3, RAW, STAGING, MARTS).
**Important:** Freshness targets should differ by source. Telemetry is expected within minutes, while daily snapshots and diesel prices are expected once per day.

#### KPI 61: Pipeline Success Rate
  **Formula:**
Pipeline Success Rate (%) = Successful runs / Total scheduled runs × 100
**Sources:** Airflow DAG runs, Airbyte sync jobs, dbt run and dbt test results.

#### KPI 62: dbt Test Pass Rate
  **Formula:**
Test Pass Rate (%) = Passing dbt tests / Total dbt tests × 100

#### KPI 63: External API Success Rate
  **Formula:**
API Success Rate (%) = Successful requests / Total requests × 100
**Sources:** Open-Meteo, EIA (and OSRM if `fetch-routes` is used). The generator falls back to labelled synthetic data when an API fails, so also track the `source` field (`open-meteo` vs `synthetic`, `eia` vs `model`).

#### KPI 64: Warehouse Cost
  **Definition:** Snowflake credits used per week, and storage size. Track against a Resource Monitor limit.
---

## 5. Recommended Dashboard Structure (Power BI)
  Use a few purposeful dashboards instead of one crowded page.
  **Performance tip:** Telemetry produces millions of rows per day at the default fleet size. Do not import raw telemetry into Power BI. Aggregate it in dbt first (per truck per hour, or per trip), and let Power BI read the aggregated tables.

### Dashboard 1: Executive Overview
  **Audience:** Management.
**KPIs:** OTD, Late Delivery Rate, Fuel Cost per Mile, Revenue per Mile, Shipment-Level Cold Chain Compliance, Truck Availability, Total Maintenance Cost, Incidents per Million Miles.
**Questions answered:** Is the operation healthy? Which KPI got worse? Where should we look first?

### Dashboard 2: Delivery & Route Performance
  **Audience:** Dispatch and customer service.
**KPIs:** OTD, On-Time Pickup, Average Delay, Severe Delay Rate, Queue Time, Dock Time, Duration Variance, Distance Variance.
**Visuals:** Lane heatmap (origin vs destination), worst customers table, delay by day and hour, facility waiting-time ranking.

### Dashboard 3: Cold Chain Monitoring
  **Audience:** Cold-chain operations and quality.
**KPIs:** Shipment Compliance, Excursion Count, Duration, Peak Severity, Refrigeration Failure Rate, Door-Open Exposure.
**Visuals:** Temperature timeline against the allowed range for one selected trip, excursions by trailer, excursion rate by ambient temperature, high-risk trip list.
**Important:** Show the commodity-specific range, not one universal threshold.

### Dashboard 4: Fuel & Cost
  **Audience:** Fleet finance and operations.
**KPIs:** Total Fuel Spend, Fuel Cost per Mile, MPG, Fuel Price Variance, Idle Fuel, Fuel Cost % of Revenue, Margin Proxy.
**Visuals:** Spend trend, MPG ranking for comparable trucks, price by state, fuel purchase outliers.

### Dashboard 5: Fleet Utilization & Driver Safety
  **Audience:** Fleet safety and operations.
**KPIs:** Utilization, Miles per Truck per Day, Speeding Events per 100 Miles, Excessive Idling Events, Route Deviation Rate, Incident Rate, Claim Cost.
**Visuals:** Time-in-state breakdown, trucks with repeated risk events, incident types and states, route deviation map.

### Dashboard 6: Maintenance & Reliability
  **Audience:** Maintenance managers.
**KPIs:** Total Maintenance Cost, Downtime Hours, Orders per Truck, Cost per Mile, Maintenance Mix, Availability.
**Visuals:** Cost trend, maintenance type breakdown, repeat-order trucks, age vs cost.

### Dashboard 7: Data Platform Health
  **Audience:** Data engineers (the team).
**KPIs:** Throughput, End-to-End Latency, Reconciliation Gap, Freshness, Duplicate Rate, Rejection Rate, Completeness, Pipeline Success Rate, dbt Test Pass Rate, API Success Rate, Snowflake Credits.
**Visuals:** Pipeline run history (Airflow), Airbyte sync status, row counts by layer, credits trend.
---

## 6. Required Dimensions and Relationships
  Dimensions every KPI should be sliceable by:
  - Date, hour, and day of week.
  - Truck (make, model year, tank size) and trailer (Refrigerated or Dry Van).
  - Driver.
  - Trip, load, and route.
  - Customer (type, freight type, account status) and booking type.
  - Facility, origin city/state, destination city/state.
  - Fuel stop city/state.
  - Maintenance type and incident type.
  - Weather condition.
  Key relationships:
  1. A **load** belongs to one customer and one route.
  1. A **trip** moves one load using one truck, one trailer, and one driver.
  1. Each trip has two **delivery events** (Pickup and Delivery), each at a facility.
  1. **Fuel purchases**, **maintenance records**, and **safety incidents** link to trucks (and trips or drivers where available).
  1. **Telemetry** links to trucks through `vehicle_id` (= `trucks.truck_id`). It has **no** `trip_id`, so it must be matched to trips using `vehicle_id` plus the time window `dispatch_ts` to `arrival_ts`.
  1. **Reefer** readings link to trucks and trailers through `vehicle_id` and `trailer_id`, and to loads through the same time-window match.
  1. **Weather** has no truck key. Match it by nearest city and hour.
  1. **Anomaly labels** link to trucks and trips and are used only for evaluation.
  Where no direct key exists, the matching rule must be documented, tested, and monitored, not silently assumed.
---

## 7. Data Engineering Requirements Before KPI Implementation

### 7.1 Preserve Raw Data
  - Keep the S3 files exactly as received (Bronze layer).
  - Keep `event_ts` and `ingest_ts` as separate columns.
  - Never clean data in place. Clean it in dbt staging models.

### 7.2 Define Event Time Correctly
  - Event time (`event_ts`): when the device recorded the reading. Use it for all KPI calculations.
  - Ingestion time (`ingest_ts`): when the platform received it.
  - Processing time: when Airbyte or dbt handled it.
  - Allow for late events (about 1% arrive 2 to 15 minutes late).

### 7.3 Deduplicate
  - Streams: keep one row per `event_id`.
  - Batch: keep one row per primary key (about 0.3% of rows in five tables are duplicated).
  - Dimension snapshots (trucks, trailers, drivers, customers, facilities, routes) repeat every day. Keep the latest, or model them as slowly changing dimensions.

### 7.4 Standardize Dirty Data
  - Trim spaces and fix text case in `customer_name`, `load_status`, `booking_type`, `trip_status`, `location_city`, `facility_location`.
  - Convert empty strings to null.
  - Handle null foreign keys (about 2% in `trips` and `fuel_purchases`): flag them, and recover from related tables where possible.
  - Quarantine malformed JSON instead of dropping it silently.

### 7.5 Validate Telemetry Quality
  - Validate GPS ranges, and treat null `lat/lon/speed_mph` as missing, never zero.
  - Detect out-of-order events using `source_sequence`.
  - Flag implausible values (speed, engine temperature, fuel level).
  - Keep a flag for any imputed value.

### 7.6 Define Cold Chain Rules
  - Create the commodity-range seed table (setpoint to allowed range).
  - Define the minimum excursion duration and the sensor-gap rule.
  - Separate confirmed excursions from suspected ones caused by missing readings.

### 7.7 Make Fuel Metrics Defensible
  - Purchased fuel is not consumed fuel. Pick one method and document it.
  - Compare prices within the same state.
  - Match each purchase to the reference price of the same date.

### 7.8 Make Idempotent Loads
  - Airbyte and replays can deliver the same data twice. Use incremental dbt models with unique keys so replays never double-count.
---

## 8. Known Limitations of the Simulated Data
  Read this before interpreting any result. The data is synthetic, so some real-world relationships do not exist, and finding them absent is not a bug.
| Area | What to expect | Why |
|---|---|---|
| Weather vs delays, speed, fuel | Likely no real relationship | Weather only drives the reefer temperature model. Traffic congestion is random and does not depend on weather. |
| Driver safety differences | Weak differences between drivers | Incidents are generated randomly by miles driven, not by driver behavior. Only about 8% of trucks drive faster, so speeding is the one real behavior signal. |
| Maintenance vs truck age | Weak or none | Maintenance orders are random per truck (about 8 per truck per year). |
| Customer-level analysis | Small samples per customer | There are thousands of customers and loads are assigned randomly. Analyze by customer type or freight type instead. |
| Utilization | Low by design | Trucks wait about 60 hours on average between loads (`WAIT_MEAN_HOURS`). |
| Road speed limits | Not available | Speeding uses a fixed threshold. |
| Harsh braking | Not reliable | There is no accelerometer, and speed is smoothed between readings. Skip it, or treat it as a weak approximation. |
| Planned route geometry | Not stored | Route deviation must be computed against a straight line between facilities. |
| Alert timestamps | Not available | The source has no alerting system, so real detection latency needs our own detection job. |
| Reefer limits | Not in the stream | Allowed ranges are simulation assumptions and must come from our seed table. |

---

## 9. Expected Baselines from the Generator Configuration
  Use these only as **sanity checks** to confirm the pipeline is correct. They come from generator parameters, not from business targets and not from measured results. If a KPI is far from its baseline, check joins and deduplication first.
| Check | Expected from configuration |
|---|---|
| Share of refrigerated loads | About 50% of loads |
| Commodity mix on reefer loads | About 10% Pharma, 45% Chilled, 45% Frozen |
| Fuel economy per truck | Between about 5.8 and 7.8 MPG |
| Refuel trigger | About 18% tank level |
| Maintenance orders | About 8 per truck per year |
| Incident rate | About 1.4 per million miles |
| Aggressive (faster) trucks | About 8% of the fleet |
| Injected anomalies | Excessive idling on about 15% of trips over 100 miles, route deviation on about 10% of trips over 150 miles, refrigeration failure on about 12% of reefer trips |
| Duplicate batch rows | About 0.3% |
| Duplicate stream events | About 0.4% |
| Null foreign keys | About 2% |
| Late stream events | About 1% |
| Malformed JSON | About 0.02% |

---

## 10. KPI Governance
  Before a KPI appears on an executive dashboard, document:
  1. Business owner (the team member responsible).
  1. Business question.
  1. Formula and unit.
  1. Numerator and denominator.
  1. Eligible records and exclusions.
  1. Source tables and columns.
  1. Reporting grain and dimensions.
  1. Refresh frequency.
  1. Target or threshold, if agreed.
  1. Data-quality checks and known limitations.
  **Do not invent targets.** If you show a target (for example OTD 95%), label it as illustrative unless the team agrees on it.
  If a calculation, eligibility rule, or source changes, record the change in the Decision Log and note the impact on historical comparison.
---

## 11. Recommended MVP Scope

### Phase 1: Core KPIs
  1. On-Time Delivery Rate and On-Time Pickup Rate.
  1. Average Delivery Delay and Late Delivery Rate.
  1. Total Recorded Fuel Expenditure.
  1. Fuel Efficiency (MPG) from trips.
  1. Revenue per Mile.
  1. Total Maintenance Cost and Maintenance Downtime.
  1. Incident Rate and Claim Cost.
  1. Shipment-Level Cold Chain Compliance, Excursion Count and Duration.
  1. Pipeline Success Rate, Row Count Reconciliation, and Data Freshness.

### Phase 2: Advanced Operational Analytics
  1. Fuel Cost per Mile (consumption-based) and Fuel Price Variance.
  1. Idle Fuel and Idle Time Share.
  1. Queue Time and Dock Time analysis.
  1. Trip Duration and Distance Variance.
  1. Truck and Trailer Utilization.
  1. Speeding Event Rate and Excessive Idling Events.
  1. Route Deviation Rate.
  1. Weather and ambient-temperature analysis.
  1. Anomaly Detection Precision and Recall.
  1. Operating Margin Proxy.

### Phase 3: Predictive and Prescriptive Analytics
  1. Predict late deliveries.
  1. Predict refrigerated loads at risk of excursion.
  1. Detect unusual fuel purchases.
  1. Identify trucks at elevated maintenance risk.
  1. Estimate cost savings from proposed operational changes.
  Predictive models should start only after the data has enough history and a clear evaluation method, and a prediction must always be distinguishable from an observed event.
---

## 12. Final Recommendations
  1. **Build from business questions, not charts.** Every KPI should support a decision.
  1. **Fix data quality first.** Duplicates, null keys, and late events will silently distort KPIs if they are not handled in staging.
  1. **Reconcile every layer.** Compare row counts between S3, Snowflake RAW, and dbt models from day one.
  1. **Separate facts from derived metrics.** A fuel purchase is not fuel consumed, and a time-window match is not a recorded trip key.
  1. **Aggregate before the dashboard.** Do not send raw telemetry to Power BI.
  1. **Do not overclaim causes.** Check Section 8 before explaining any result.
  1. **Use comparable denominators.** Normalize events by miles, and compare similar trucks and lanes.
  1. **Use ground truth only to evaluate,** never inside the detection rules.
  1. **Write a data contract per source.** Document schema, keys, timestamp meaning, volume, refresh rate, and failure behavior (the Data Catalog is the starting point).
  1. **Measure impact, not only output.** The goal is better delivery performance, protected cargo, and lower avoidable cost.
- ▸ **Q&A**

## ❓ Team Q&A: How the Fleet Generator Works
---

### Q1. What does `fleet_generator.py` do, and how does the data flow from start to end?
  **Short answer:** It is a simulator. It pretends to be a fleet of 5,000 US trucks and creates data like real systems would (GPS devices, fuel cards, maintenance shops). 
  **Flow, step by step:**
  1. **Setup:** The code creates cities, routes, warehouses, customers, trucks, trailers (some refrigerated, some normal), and drivers.
  1. **Outside data:** It calls the Open-Meteo API (real weather) and, if we give an API key, the EIA API (real diesel price). The raw responses are saved to S3 as they are.
  1. **Simulation loop:** Every "tick" (1 minute by default) the simulated world moves one step. Trucks drive, burn fuel, take breaks, load, unload, and sometimes have accidents or go to maintenance. Refrigerated trailers heat up or cool down based on the real outside temperature.
  1. **Two data paths:**
    - **Streaming data** (GPS, speed, engine, fuel level, trailer temperature): one JSON message per truck per tick.
    - **Batch data** (trips, loads, fuel purchases, maintenance, incidents, master data): collected in memory, then saved as `CSV.gz` files.
  1. **Destination:** Everything lands in S3 (the Bronze or raw layer). Streaming data can also go to Kafka, but we are not using Kafka, so all of it goes to S3.
---

### Q2. What does the generator change or break on purpose?
  It adds real-world problems:
| Problem | What happens | Example |
|---|---|---|
| Sensor noise | Small random changes are added to readings | GPS and speed are never perfect |
| Missing values (null) | Some values are removed | GPS or speed becomes null. `driver_id` or `truck_id` disappears in trips and fuel purchases |
| Text mess | Text is changed in a few rows | `Completed` becomes `completed`, `COMPLETED`, or `Completed ` (extra space) |
| Late messages | A few messages arrive 2 to 15 minutes late | Time order gets mixed up |
| Duplicates | A few rows or messages are sent twice | Same `event_id` appears two times |
| Broken JSON | Very rare | A message is cut, or `event_ts` is renamed to `event_tz` |
| Injected problems (anomalies) | Real "bad events" are created | Truck leaves its route, truck idles for a long time, refrigeration unit fails |

  The generator also writes the correct answer for each injected problem into a separate folder (`ground_truth`). We only use it to check our detection rules.
---

### Q3. A trip can take 10 hours. What is sent every 15 minutes?
  **Short answer:** The trip is **not** sent while it is running. It is sent only after it is finished.
  - **While the truck drives:** a GPS and engine message is sent every minute (streaming path).
  - **When the truck finishes unloading:** the generator writes **one row** in the `trips` table. This is a final summary of the whole trip.
  - **The 15 minutes** is just how often the generator packs the finished records into a file. Think of it as a mail truck that leaves every 15 minutes. In each file you find only the records that finished since the last file: finished trips, fuel purchases, maintenance jobs, and incidents.
  So a 10-hour trip does not appear in 40 files. It appears **once**, in the file made after it finished.
---

### Q4. Why do we need the `trips` table, and what columns does it have?
  **Why:** It connects the **business side** (which load, which customer) with the **physical side** (which truck, trailer, and driver, how many miles, how much fuel). Without it, we have GPS data on one side and orders on the other side and no way to connect them.
| Group | Column | Meaning |
|---|---|---|
| Keys | `trip_id` | Unique trip ID |
|  | `load_id` | The load (order) carried on this trip |
|  | `driver_id`, `truck_id`, `trailer_id` | Who and what did the trip |
| Time | `dispatch_date` | Date the trip started |
|  | `dispatch_ts` | When pickup (loading) started |
|  | `arrival_ts` | When the truck arrived at the destination |
| Numbers | `actual_distance_miles` | Miles driven |
|  | `actual_duration_hours` | Hours from pickup start to arrival |
|  | `fuel_gallons_used` | Gallons burned by the truck engine |
|  | `average_mpg` | Miles per gallon |
|  | `idle_time_hours` | Hours the engine was on while the truck was not driving (includes time at the dock) |
| Status | `trip_status` | Status of the trip |

---

### Q5. What values can `trip_status` have? Is it in another table?
  **Real value:** only `Completed`, because we only write finished trips.
  **Values you will actually see (because of dirty data):**
  - `Completed`
  - `completed`
  - `COMPLETED`
  - `Completed ` (with a space at the end)
  All four mean the same thing. We fix this in the dbt staging model (trim spaces and make the case the same).
  **Other tables:** `trip_status` exists only in `trips`. Other tables have their own status columns:
| Table | Column | Values |
|---|---|---|
| loads | `load_status` | `Completed` (same dirty versions) |
| trucks | `status` | `Active`, `Maintenance` |
| drivers | `employment_status` | `Active`, `Terminated` |
| customers | `account_status` | `Active`, `Inactive` |

---

### Q6. A trip can stop for rest, fuel, or an accident. Where is that saved?
  The `trips` table is only the final summary, so it does not change when something happens during the trip. Each event goes to its own place and is linked by `trip_id`:
| Event | Where it is saved |
|---|---|
| Accident or violation | New row in `safety_incidents` (has `trip_id`) |
| Fuel stop | New row in `fuel_purchases` (has `trip_id`) |
| Long idling (injected problem) | A label in `ground_truth/gen_anomaly_labels` (has `trip_id`) |
| Rest break | Not in a batch table. You see it in telemetry: the engine is off and speed is 0 |
| Short stop (30-minute break) | Telemetry: engine on and speed 0 |
| Traffic | Telemetry: speed becomes lower than normal |

  **To see the full story of one trip:** join `trips` with `safety_incidents`, `fuel_purchases`, and telemetry.
  **Important:** Telemetry has **no** `trip_id`. Join it using `vehicle_id` and the time between `dispatch_ts` and `arrival_ts`.
---

### Q7. Which tables come as streams, and which come as batches?
| Type | Data | Format | Where it goes |
|---|---|---|---|
| **Stream** | Telemetry (GPS, speed, engine) and Reefer (trailer temperature) | JSON | Kafka, or S3 directly |
| **Batch** | trips, loads, delivery_events, fuel_purchases, maintenance_records, safety_incidents, customers, facilities, routes, trucks, trailers, drivers, diesel_prices | CSV.gz every 15 minutes | S3 |
| **Reference** | Weather and diesel price from APIs | JSON | S3 |
| **Truth** | Anomaly labels | JSONL | S3 |

---

### Q8. Why don’t we include `load_id` and `trip_id` inside the stream data, so we know the trip status. Is this a good idea?
  **Our opinion: No, not in the raw layer.**
  **Reasons:**
  1. **Real devices do not know it.** A GPS device in a truck knows only its own ID, location, speed, and temperature. It does not talk to the transport system (TMS), so it does not know the load or the trip.
  1. **Keep things separate.** If a trip is cancelled or the truck gets a new load, we should not need to change the device messages.
  1. **Raw data should stay raw.** In the Bronze layer we keep data exactly as the source sent it. This helps us trace any number back to its source.
  **What to do instead:** Add the trip information later, in dbt/Snowflake (Silver layer). Join telemetry with trips using `vehicle_id` and the time window (`dispatch_ts` to `arrival_ts`). The result is a clean table where each GPS point has its `trip_id`.
---

### Q9. Is it realistic that some trucks write directly to S3 and not through Kafka? Should everything go to Kafka?
  **Short answer:** Yes, it is a realistic idea. In books, all sensor data goes through Kafka, but real life is messier.
  **Why:**
  - Trucks drive through areas with no network. The device saves readings inside itself.
  - When the network comes back, the device may send a big file of old readings at once. Sending thousands of old messages to Kafka at once can overload it, and Kafka is made for small, fresh messages.
  - So many systems upload this kind of data as a **file directly to S3**.
  **In our generator:**
  - `DIRECT_S3_PCT` sets the share of trucks that write directly to S3 (default 10%). Their messages are saved as files every 10 minutes.
  - Old data from a backfill (older than 24 hours) also goes straight to S3.
  - The data from these trucks arrives later, so always use `event_ts` (when it happened) and not `ingest_ts` (when it arrived).
  **For our project:** We are not using Kafka, so we set `KAFKA_MODE=null` and `DIRECT_S3_PCT=100`. This sends all stream data to S3, and Airbyte can read it from there.
- ▸ **Documentation**
  [Documentation](https://app.notion.com/p/3ff961599a4880dc9232c35ae49c5409) (not publicly shared, so not included here)
---
