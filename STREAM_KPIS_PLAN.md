# Plan: stream KPIs + moving trucks, all from Kafka ⏳ (steps 1–2 ✅, step 3 ⬜)

**Status:**
- Step 1 (backend KPIs + charts) ✅ done 2026-10-29: [WORK_LOG.md](WORK_LOG.md), "Stream KPIs + moving trucks from Kafka".
- Step 2 (pages show them) ✅ done 2026-10-29: [WORK_LOG.md](WORK_LOG.md), "Dashboard pages show the stream KPIs (step 2)".
- Step 3 (map replay, section 4) ⬜ not started.

Answers to section 7: Q1–Q4 yes, Q5 normal summary + flow.

**Goal:** every KPI and chart that depends on telemetry / reefer data is calculated from the Kafka silver topics
(not the warehouse), sent over `GET /api/stream`, and updated on the page when a new Kafka batch arrives.
The live map trucks move continuously instead of one 5 s glide every 5 min.

**Decisions already taken (2026-10-29):**
| # | Decision |
|---|---|
| 1 | Map: **replay by `event_ts`** (every Kafka row is sent, trucks glide through their real rows) |
| 2 | KPI window: **last 60 min vs previous 60 min** |
| 3 | No `trip_id` / `load_id` in Kafka: use **trailer (reefer) / truck (telemetry) inside the window** instead of a trip, written as an assumption |
| 4 | Scope: **map + KPI cards + charts** |
| 5 | KPIs 35 (route deviation) and 51–53 (detection quality) have no data source: **removed from the dashboard** (2026-10-29) |

---

## 1. Facts this plan is built on (measured 2026-10-29, read-only)

| Fact | Value | Meaning |
|---|---|---|
| Today, stream KPIs on the pages | `null` (`-`) | The warehouse has no telemetry / reefer table. Nothing is calculated today |
| Batch from upstream | every **5 min**, ~**2,145** telemetry + ~**1,180** reefer rows | Data reaches Kafka (and us) only every 5 min |
| Spread of `event_ts` inside one batch | **99 %** of rows within **5 min** of the batch's newest `event_ts` | One batch = the last 5 min of data |
| Age of the newest row when it arrives | ~**10 min** | Upstream lag, not ours |
| Rows of one truck | every **5 min** (median), p90 25 min (parked trucks report less) | Replay must wait ~1 batch to always have the "next" row |
| Movement between 2 rows (driving) | median **4.4 mi** = **0.064** scene units = **26 %** of a truck model length | Why the map looks frozen today |
| Rows in 120 min (both topics) | **80,139** rows: **223 MB** as full Python dicts, 50 MB raw JSON | Keeping full rows is too heavy → keep only the needed columns |
| Kafka retention | oldest message ~13 h back | 120 min of history is safe |
| `trip_id`, `load_id`, `driver_id` in Kafka | **not present** | Decision 3; per-driver columns stay null |

---

## 2. Design (big picture)

```
Kafka (2 topics) ──► KafkaStreamSource ──► StreamService._read()
                                              │  FleetState.apply(kind, row)
                                              ▼
                       FleetState (memory) ─────────────────────────────────────────────
                       • latest row per truck        (as today: alerts, Live KPIs panel)
                       • NEW: every row, last 120 min, only needed columns (StreamHistory)
                                              │ every 1 s, only when new rows came
                                              ▼
              take_changes(): telemetry/reefer (NOW: every new row, not only the latest)
                              alert, kpis (as today)
                              NEW stream_kpis: {period, kpis: [KpiValue], series: {...}}
                                              │
                                   GET /api/stream (SSE)
                    ┌─────────────────────────┴───────────────────────────┐
             Live map page                                     Cold Chain / Fuel / Safety / Executive
   useFleetState: rows per truck                         DashboardShell: warehouse cards (REST, 30 min)
   TruckLayer: replay clock, glide                       + stream_kpis event fills the stream KPIs/charts
   between the 2 rows around the clock                     (stream value wins over the REST null)
```

### 2.1 Why these choices
- **One more SSE event (`stream_kpis`) instead of a new REST endpoint:** you asked for the stream endpoint and live
  updates. The values change only when a Kafka batch arrives, which the stream already knows.
- **Calculated in the backend, not the browser:** same rule as the warehouse KPIs ("backend calculates, frontend
  displays"), and the browser would need all 80k rows to do it.
- **Compact history (only needed columns):** full rows = 223 MB. Only ~10 columns per row are needed for the KPIs.
- **Window ends at the newest `event_ts`, not at the wall clock:** data is ~10 min old on arrival. A wall-clock window
  would always have an empty last 10 min. Same rule as the alerts ("every time rule uses `event_ts`").
- **Replay delay = 1 batch gap (5 min) measured from the data, no config:** the clock shows `newest event_ts − gap`,
  so every truck always has its next row already. With a faster upstream (or the mock), the gap shrinks by itself.

---

## 3. KPIs from Kafka (window = last 60 min of `event_ts`; previous = the 60 min before)

"Interval" of a row = time to the next row of the same truck/trailer, **capped at 15 min** (so one missing row
does not count as hours). Excursion = **≥ 2 consecutive** reefer rows of one trailer with `is_temp_breach`
(rows with null `cargo_temp_f` are skipped, catalog A.6). A run that begins with the first kept row is skipped (its start is unknown);
the backend keeps **30 extra minutes** before the previous window so its runs have a known start (found on real data: KPI 34 was 49 vs 153 without it).

| KPI | Page | Unit | Rule from Kafka columns | Assumption |
|---|---|---|---|---|
| 10 Cold Chain Compliance (readings) | Cold Chain | % | reefer rows with `cargo_temp_f` not null and not `is_temp_breach` / rows with `cargo_temp_f` not null × 100 | — |
| 11 Shipment Cold Chain Compliance | Executive, Cold Chain | % | trailers with no excursion / all trailers in the window × 100 | trailer = load |
| 12 Temperature Excursions | Cold Chain | count | excursions that start in the window | — |
| 13 Avg Excursion Duration | Cold Chain | min | average (last breach row − first breach row) | — |
| 14 Peak Excursion Severity | Cold Chain | °F | average per excursion of max(`cargo_temp_f` − `allowed_temp_max_f`, `allowed_temp_min_f` − `cargo_temp_f`) | — |
| 15 Refrigeration Failure Rate | Cold Chain | % | trailers with any `is_reefer_unit_failure` row / all trailers × 100 | trailer = trip; silver flag instead of compressor rule |
| 16 Door-Open Exposure | Cold Chain | min/trip | Σ interval of `door_open` rows / trailers | trailer = trip |
| 23 Idle Fuel | Fuel | L | Σ `fuel_gph` × interval (h) × 3.78541 for `is_idling` rows | — |
| 29 Truck Utilization | Safety | % | Σ interval of `DRIVING` rows / Σ interval of all rows × 100 | no loading/unloading in Kafka |
| 33 Speeding Events | Safety | per 100 km | runs of consecutive `is_speeding` rows / km driven × 100; km = Σ per truck (max − min `odometer_mi`) × 1.609344 | 1 row is enough for an event (rows are 5 min apart) |
| 34 Excessive Idling Events | Safety | count | runs of `is_idling` that reach 30 min, counted when they reach it (same moment as the `EXCESSIVE_IDLING` alert) | — |
| 35, 51, 52, 53 | — | — | removed | no data source |

### Charts from Kafka (same window)
| Series | Page | Shape (same as the mock, see `dashboard/src/data/mock/dashboards.js`) |
|---|---|---|
| `trip_temperature` | Cold Chain | readings (`event_ts`, `cargo_temp_f`, `setpoint_f`) of the trailer with the longest excursion; `trip_id` = null, title shows the trailer |
| `excursions_by_trailer` | Cold Chain | top 10 trailers by excursion count |
| `excursion_rate_by_ambient` | Cold Chain | KPI 17 per band (< 50, 50–70, 70–90, > 90 °F), trailer band = its average `ambient_temp_f` |
| `high_risk_trips` | Cold Chain | top 8 excursions by duration (`trip_id` null) |
| `time_in_state` | Safety | share of time (%) per `motion_status`: Driving / Idling / Parked (Kafka has only these 3) |

Removed (need data Kafka does not have): `kpi_33` / `kpi_34` per driver in `driver_scorecard` (no `driver_id`),
`kpi_11` per week in `service_trend` (Kafka keeps ~13 h, not weeks).

---

## 4. Moving trucks (replay)

- **Backend:** `take_changes()` sends **every new row** (not only the latest per truck). Snapshot sends, per truck,
  its last row before `newest − gap` plus every row after it (~2 rows per truck).
- **Frontend `useFleetState`:** keeps a short sorted list of rows per truck (drops rows the clock has passed).
- **Replay clock:** `clock = newest event_ts received − gap`, then runs at real speed (1 s per s), and never passes
  the newest row (trucks wait instead of guessing).
- **`TruckLayer`:** every frame, each truck is drawn between its row before the clock and the row after it
  (position and heading interpolated). Jumps > 1 scene unit (~69 mi) are drawn as a jump, as today.
- **Selected truck panel / colors:** the row the truck is on at the clock. Alerts and Live KPIs use the newest data,
  so they are ~5 min ahead of the map (shown in the subtitle).
- **Honest limit:** real speed at country zoom is slow (~4 mi per 5 min). Movement is clear when zoomed in.

---

## 5. Files (planned)

| File | Change |
|---|---|
| `backend/app/services/stream_history.py` (new) ✅ | Compact rows of the last 2 × `STREAM_HISTORY_MINUTES` + 30 min, dedup, expire |
| `backend/app/services/stream_kpis.py` (new) ✅ | Pure functions: rows → KPI values and series (testable with dicts) |
| `backend/app/services/fleet_state.py` | Feed the history, build `stream_kpis` ✅ · send every new row, snapshot for replay (step 3) ⬜ |
| `backend/app/schemas/stream.py` ✅ | `StreamKpis` model, `EventName` (`?events=` filter in `api/routes/stream.py` ✅) |
| `backend/app/services/stream_service.py` ✅ | Read back 150 min on start (2 windows + 30 min) |
| ~~`dashboard/src/hooks/useStreamKpis.js` (new)~~ | Not needed: `DashboardShell` calls the existing `useStream('stream_kpis', ...)` (one line) |
| `dashboard/src/components/DashboardShell.jsx` ✅ (`KpiCard.jsx` unchanged) | Merge stream values over REST nulls ✅; instead of a tag per card, the header shows a 2nd period line "Live (Kafka): …" (owner's choice) |
| `dashboard/src/data/api/apiSource.js` ✅ (added) | `?events=` of the subscribed event types, one reconnect per page change, close on `pagehide` |
| `dashboard/src/hooks/useFleetState.js`, `scene/TruckLayer.jsx`, `pages/LiveMapPage.jsx` | Replay |
| `dashboard/src/pages/ColdChainPage.jsx` ✅ | Title when `trip_id` is null |
| `dashboard/src/data/contract.js`, READMEs, `ARCHITECTURE.md`, `WORK_LOG.md` | Docs |

- **`.env`:** no change. `STREAM_HISTORY_MINUTES=60` stays; the KPI window = 60 and the backend keeps 2 × 60 + 30 min (~42 MB).
- **Database:** no change.

## 6. Tests (planned)
- Pure functions with fake rows: each KPI rule, excursion runs (1 row = no excursion, 2 rows = 1), interval cap,
  window edges, null `cargo_temp_f`, duplicates.
- Real Kafka: values printed for one window, memory of the history, snapshot size, `stream_kpis` size.
- Browser (headless Edge, as before): cards filled on Cold Chain / Fuel / Safety / Executive, trucks moving between batches.
- `npm run build`.

---

## 7. Open questions for you
| # | Question | My recommendation |
|---|---|---|
| Q1 | Non-map pages only need `stream_kpis` (a few KB), but the stream also sends all rows (~6 MB snapshot + ~2 MB per batch). Add an optional filter `GET /api/stream?events=stream_kpis`? | **Yes** (one endpoint, small change) |
| Q2 | History keeps only the needed columns (~10 per row) instead of full rows (223 MB)? | **Yes** |
| Q3 | Interval cap 15 min for KPIs 16, 23, 29 OK? | **Yes** |
| Q4 | Work in 3 steps, each reviewed by you: (1) backend KPIs + charts, (2) pages show them, (3) replay map? | **Yes** |
| Q5 | Do you want the deep line-by-line explanation (markdown) for each step, or the normal summary? | your choice |
