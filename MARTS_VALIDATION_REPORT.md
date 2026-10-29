# DBT_MARTS Validation Report

**Database:** `SUPPLYCHAIN_DW.DBT_MARTS` (read with user `AIRFLOW_USER`, role `AIRFLOW_ROLE`)
**Scope:** all rows, no date filter. Read-only: nothing was changed in Snowflake.

> Counts are a snapshot from 2026-10-29. Data loads every 15 minutes, so recent counts will move.

---

## 1. Summary

We ran **53 checks** on the mart tables:

| Status | Checks | Meaning |
|---|---|---|
| ✅ PASS | 40 | Key is clean |
| ⚠️ WARN | 9 | Some rows have an empty (NULL) key: the row does not point to anything |
| ❌ FAIL | 4 | Some rows point to a parent that does not exist (orphan) |

**Verdict:** the model structure is sound. All primary keys are unique, all dimension links work, and every customer and driver has exactly one current row. The FAILs and WARNs come from **4 root causes**, listed below by priority.

| # | Root cause | Rows affected | Where to fix | Priority |
|---|---|---|---|---|
| 1 | `FCT_MAINTENANCE.FACILITY_KEY` is always NULL | 106,524 (100%) | dbt model | 🔴 High |
| 2 | Loads from 29–31 Dec 2023 removed from `FCT_SHIPMENTS`, but their events and fuel are kept | 3,900 events + 807 fuel purchases | dbt model + source | 🔴 High |
| 3 | Events, fuel and incidents of trips not finished yet | 1,336 events + 3,546 fuel + 6 incidents | Decision needed | 🟡 Medium |
| 4 | ~2% of source trips have no truck, driver or trailer | ~19,000 trips + ~37,000 fuel purchases | Source (generator) | 🟢 Low (confirm only) |

---

## 2. Issues

### Issue 1: `FCT_MAINTENANCE.FACILITY_KEY` is always NULL 🔴

| | |
|---|---|
| **Check** | WARN `FCT_MAINTENANCE.FACILITY_KEY -> DIM_FACILITY.FACILITY_KEY` |
| **Rows** | 106,524 of 106,524 (100%) |
| **Examples** | `MAINT00008326` (`FACILITY_LOCATION` = `Seattle`), `MAINT00008327` (`Pittsburgh`), `MAINT00008328` (`Columbus`) |

**What is wrong:** the column exists in the model but is never filled.

**Evidence:** the source `RAW_DATA.MAINTENANCE_RECORDS` has only `FACILITY_LOCATION`, which is a **city name** (25 distinct values). It has no facility ID. `DIM_FACILITY` has 50 facilities, named like `Memphis Warehouse 26`. A city matches 0 facility names, and one city can hold several facilities, so the key cannot be found. `LOCATION_KEY` (the city) **is** filled correctly.

**KPI impact:** maintenance cost and downtime cannot be shown by facility (Maintenance dashboard). By city still works through `LOCATION_KEY`.

**Suggested fix (owner decides):** remove `FACILITY_KEY` from `FCT_MAINTENANCE` and use `LOCATION_KEY`, **or** document a rule that maps a city to one facility.

```sql
SELECT COUNT(*) AS rows_total, COUNT(facility_key) AS rows_with_facility_key
FROM fct_maintenance;
```

---

### Issue 2: Loads from 29–31 Dec 2023 removed, but their events and fuel are kept 🔴

| | |
|---|---|
| **Checks** | FAIL `FCT_DELIVERY_EVENTS.LOAD_ID -> FCT_SHIPMENTS.LOAD_ID` · FAIL `FCT_DELIVERY_EVENTS.TRIP_ID -> FCT_TRIPS.TRIP_ID` · FAIL `FCT_FUEL_PURCHASES.TRIP_ID -> FCT_TRIPS.TRIP_ID` · WARN NULL `CUSTOMER_ID`, `ROUTE_ID`, `LOAD_DATE_KEY` in `FCT_DELIVERY_EVENTS` |
| **Rows** | 3,900 delivery events (2,046 dated 2023-12, 1,854 dated 2024-01) · 807 fuel purchases dated 2024-01 (447,916.57 USD) |
| **Examples** | Events `EVT00000003` (`LOAD00000119` / `TRIP00000119`), `EVT00000009` (`LOAD00000694`). Fuel `FUEL000000001` (`TRIP00000738`), `FUEL000000002` (`TRIP00000619`) |

**What is wrong:** these rows belong to the first 1,950 loads (`LOAD00000001` – `LOAD00001950`).

**Evidence:**
| Table | Has loads/trips 1–1950? |
|---|---|
| `RAW_DATA.LOADS` | ✅ Yes. All 1,950 loads, `LOAD_DATE` 2023-12-29 to 2023-12-31 |
| `FCT_SHIPMENTS` | ❌ No. Starts at `LOAD00001951`, `LOAD_DATE` 2024-01-01 → dropped in dbt (looks like a `LOAD_DATE >= 2024-01-01` filter) |
| `RAW_DATA.TRIPS` | ❌ No. Starts at `TRIP00001951` → never produced by the source |
| `FCT_DELIVERY_EVENTS`, `FCT_FUEL_PURCHASES` | ⚠️ Yes. The child rows of those loads/trips are kept |

So the parent is cut off at 2024-01-01 but the children are not. Because the load is missing, dbt also leaves `CUSTOMER_ID`, `ROUTE_ID` and `LOAD_DATE_KEY` empty on the same 3,900 events (the 3 WARNs).

**KPI impact:** on-time delivery by customer or route, and fuel cost per trip / Margin Proxy (KPI 28), cannot use these rows. They show as "unknown" or are dropped by inner joins.

**Suggested fix (owner decides):** apply the same date window to the child facts (drop events and fuel of loads before 2024-01-01), **or** keep the 1,950 December loads in `FCT_SHIPMENTS`. Trips 1–1950 do not exist in the source either way.

```sql
SELECT TO_CHAR(actual_date, 'YYYY-MM') AS month, COUNT(*) AS events_without_load
FROM fct_delivery_events
WHERE load_id NOT IN (SELECT load_id FROM fct_shipments)
GROUP BY 1 ORDER BY 1;

SELECT TO_CHAR(purchase_date, 'YYYY-MM') AS month, COUNT(*) AS purchases_without_trip
FROM fct_fuel_purchases
WHERE trip_id NOT IN (SELECT trip_id FROM fct_trips)
GROUP BY 1 ORDER BY 1;
```

---

### Issue 3: Child rows of trips not finished yet 🟡

| | |
|---|---|
| **Checks** | FAIL on `TRIP_ID` / `LOAD_ID` (same checks as Issue 2, recent rows only) · FAIL `FCT_SAFETY_INCIDENTS.TRIP_ID -> FCT_TRIPS.TRIP_ID` |
| **Rows (dated 2026-10-20 or later)** | 846 delivery events whose load exists but trip is missing · 490 delivery events whose load and trip are both missing · 3,546 fuel purchases · 6 safety incidents |
| **Examples** | Incidents on trips `TRIP00954539` (2026-10-25), `TRIP00956732` (2026-10-28) |

**What is wrong:** `FCT_TRIPS` holds only `Completed` trips (all 953,293 rows have `TRIP_STATUS = Completed`), and its latest `TRIP_DATE` is 2026-10-27. Events, fuel and incidents of trips still on the road arrive first, so for now they point to a trip that is not in the mart yet. For 490 recent events the load is not in `FCT_SHIPMENTS` yet either (also timing: check again after the next dbt run).

**KPI impact:** small and temporary. These rows should match once the trips complete and dbt runs again.

**Decision needed:** should facts keep child rows of unfinished trips (as now), or wait until the trip is completed? If they are kept, the `relationships` dbt test on `TRIP_ID` should ignore the last few days, so it does not fail on every run.

```sql
SELECT COUNT(*) AS purchases_without_trip,
       COUNT_IF(purchase_date >= '2026-10-20') AS recent
FROM fct_fuel_purchases
WHERE trip_id NOT IN (SELECT trip_id FROM fct_trips);
```

---

### Issue 4: ~2% of source trips have no truck, driver or trailer 🟢

| | |
|---|---|
| **Checks** | WARN NULL `TRUCK_KEY`, `TRAILER_KEY`, `DRIVER_KEY` in `FCT_TRIPS` · WARN NULL `TRUCK_KEY`, `DRIVER_KEY` in `FCT_FUEL_PURCHASES` |
| **Rows** | `FCT_TRIPS`: 19,348 / 19,099 / 18,967 of 953,293 (~2.0% each) · `FCT_FUEL_PURCHASES`: 36,987 / 37,312 of 1,852,581 (~2.0%) |
| **Examples** | `TRIP00001970` (no truck, driver `DRV04051`), `TRIP00001992` (no truck, driver `DRV01692`) |

**What is wrong:** these rows do not say which truck, driver or trailer was used.

**Evidence:** this is **not** a failed dbt lookup. On every row with NULL `TRUCK_KEY`, the `TRUCK_ID` is NULL too (19,348 of 19,348 trips, 36,987 of 36,987 fuel purchases). In `RAW_DATA.TRIPS`, 34,035 of 1,679,187 rows (2.0%) already have an empty `TRUCK_ID`. The share is ~2% in every year (2024, 2025, 2026), which looks like dirty data injected on purpose by the generator.

**KPI impact:** MPG by truck, driver safety and Margin Proxy (KPI 28) exclude these trips. Fleet totals (total fuel spend, total revenue) are not affected.

**Action:** confirm with the generator team that this is intended dirty data. If it is, no fix is needed; keep the WARN.

```sql
SELECT COUNT(*) AS trips_without_truck_key, COUNT(truck_id) AS of_which_have_truck_id
FROM fct_trips
WHERE truck_key IS NULL;
```

---

## 3. What passed ✅

| Area | Checks | Result |
|---|---|---|
| Primary keys unique | `TRIP_ID`, `LOAD_ID`, `EVENT_ID`, `FUEL_PURCHASE_ID`, `MAINTENANCE_ID`, `INCIDENT_ID`, every `DIM_*` key, and `ROUTE_ID`, `FACILITY_ID`, `TRUCK_ID`, `TRAILER_ID` | 0 duplicates |
| Fact → dimension | `CUSTOMER_KEY`, `ROUTE_KEY`, `DISPATCH_DATE_KEY` in `FCT_TRIPS`; all keys in `FCT_SHIPMENTS`, `FCT_SAFETY_INCIDENTS` (except `TRIP_ID`), `FCT_MAINTENANCE` (except `FACILITY_KEY`) | 0 orphans, 0 NULLs |
| Dimension → `DIM_LOCATION` | `DIM_ROUTE` origin and destination, `DIM_FACILITY`, `DIM_DRIVER` and `DIM_TRUCK` home terminal | 0 orphans |
| Dimension history | One `IS_CURRENT` row per `CUSTOMER_ID` (2,500) and `DRIVER_ID` (8,308) | 0 problems |
| KPI cross-check | Margin Proxy (KPI 28): maintenance cost used = 208,150,661.15 USD = full table. Fuel gap 24,203,130.11 USD = orphans 2,352,817.84 + no-truck trips 21,850,312.27 | Reconciles exactly |

---

## 4. Questions for the model owner

1. **Issue 1:** remove `FACILITY_KEY` from `FCT_MAINTENANCE`, or map city → facility?
2. **Issue 2:** is the 2024-01-01 cut on `FCT_SHIPMENTS` intended? If yes, can the same cut be applied to `FCT_DELIVERY_EVENTS` and `FCT_FUEL_PURCHASES`?
3. **Issue 3:** keep child rows of unfinished trips, or wait for the trip to be completed?
4. **Issue 4:** is the ~2% of trips with no truck, driver or trailer the generator's injected dirty data?

---

## 5. How to reproduce

All 53 checks run from one script ([tools/validate_marts.py](tools/validate_marts.py)) with the backend login (`backend/.env`, schema `DBT_MARTS`). It takes about 20 seconds and exits with code 1 if any check fails.

```bash
.venv/Scripts/python tools/validate_marts.py
```

| Status rule | Meaning |
|---|---|
| FAIL | Orphan key, duplicate key, or a history ID without exactly one `IS_CURRENT` row |
| WARN | NULL key |
| PASS | Clean |

**Raw FAIL / WARN output (2026-10-29):**

| Status | Check | Rows total | NULL keys | Orphans |
|---|---|---|---|---|
| FAIL | `FCT_DELIVERY_EVENTS.LOAD_ID -> FCT_SHIPMENTS.LOAD_ID` | 1,911,822 | 0 | 4,390 |
| FAIL | `FCT_DELIVERY_EVENTS.TRIP_ID -> FCT_TRIPS.TRIP_ID` | 1,911,822 | 0 | 5,236 |
| FAIL | `FCT_FUEL_PURCHASES.TRIP_ID -> FCT_TRIPS.TRIP_ID` | 1,852,581 | 0 | 4,353 |
| FAIL | `FCT_SAFETY_INCIDENTS.TRIP_ID -> FCT_TRIPS.TRIP_ID` | 2,422 | 0 | 6 |
| WARN | `FCT_MAINTENANCE.FACILITY_KEY -> DIM_FACILITY.FACILITY_KEY` | 106,524 | 106,524 | 0 |
| WARN | `FCT_TRIPS.TRUCK_KEY -> DIM_TRUCK.TRUCK_KEY` | 953,293 | 19,348 | 0 |
| WARN | `FCT_TRIPS.TRAILER_KEY -> DIM_TRAILER.TRAILER_KEY` | 953,293 | 19,099 | 0 |
| WARN | `FCT_TRIPS.DRIVER_KEY -> DIM_DRIVER.DRIVER_KEY` | 953,293 | 18,967 | 0 |
| WARN | `FCT_FUEL_PURCHASES.TRUCK_KEY -> DIM_TRUCK.TRUCK_KEY` | 1,852,581 | 36,987 | 0 |
| WARN | `FCT_FUEL_PURCHASES.DRIVER_KEY -> DIM_DRIVER.DRIVER_KEY` | 1,852,581 | 37,312 | 0 |
| WARN | `FCT_DELIVERY_EVENTS.CUSTOMER_ID -> DIM_CUSTOMER.CUSTOMER_ID` | 1,911,822 | 4,390 | 0 |
| WARN | `FCT_DELIVERY_EVENTS.ROUTE_ID -> DIM_ROUTE.ROUTE_ID` | 1,911,822 | 4,390 | 0 |
| WARN | `FCT_DELIVERY_EVENTS.LOAD_DATE_KEY -> DIM_DATE.DATE_KEY` | 1,911,822 | 4,390 | 0 |

**How the FAIL counts split by root cause:**
| Check | Issue 2 (Dec 2023 cut) | Issue 3 (unfinished trips) | Total |
|---|---|---|---|
| Delivery events, load missing | 3,900 | 490 | 4,390 |
| Delivery events, trip missing | 3,900 | 1,336 (846 + 490) | 5,236 |
| Fuel purchases, trip missing | 807 | 3,546 | 4,353 |
| Safety incidents, trip missing | 0 | 6 | 6 |
