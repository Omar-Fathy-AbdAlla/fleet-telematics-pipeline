// The contract between the backend and the dashboard. Documentation only (JSDoc), no runtime code.
//
// 1) Warehouse KPIs: GET {VITE_API_BASE_URL}/kpis/{dashboardId}?kpi_ids=1&kpi_ids=2...
//    dashboardId is one of the ids in src/dashboards.js, kpi_ids are that page's kpiIds. The backend calculates the values
//    in Snowflake (DBT_MARTS); the frontend only displays them. Metric units (km, L, USD), see src/kpis/definitions.js.
//    KPIs and series that are not in the warehouse (live stream, platform) come back as null.
//    The stream ones (KPIs 10-16, 23, 29, 33, 34 and their charts) come in the stream_kpis event instead (2).
//
// 2) Live stream: Server-Sent Events at {VITE_STREAM_URL} (backend: GET /api/stream), five named events:
//    event: telemetry  data: TelemetryRow[]  (only rows that changed, one batch per tick, not one message per truck)
//    event: reefer     data: ReeferRow[]
//    event: alert      data: AlertRow        (sent when an alert starts, and again with end_ts when it ends)
//    event: kpis       data: LiveKpis        (sent with every change)
//    event: stream_kpis data: StreamKpis     (sent after new Kafka messages, ~once per batch, and at least every minute)
//    On connect the backend first sends a snapshot: the latest row of every truck kept (last STREAM_HISTORY_MINUTES),
//    every active alert, the last 40 alert changes, the KPIs and the stream KPIs, so a new viewer never sees an empty page.
//    ?events=stream_kpis&events=alert sends only those events (all when empty): pages without the map need ~1 KB, not ~4 MB.
//    Source: Kafka topics fleet.silver.telemetry.v1 / fleet.silver.reefer.v1, published in batches every ~5 min today.

/**
 * @typedef {Object} DashboardResponse
 * @property {string} dashboard            dashboard id
 * @property {string} period               human label, e.g. "Last 30 days vs previous 30 days"
 * @property {string} as_of                ISO timestamp (UTC) of the last warehouse refresh
 * @property {KpiValue[]} kpis
 * @property {Object<string, any>} series  chart data; keys per dashboard are listed in DASHBOARD_SERIES (backend/app/services/kpi_service.py)
 */

/**
 * @typedef {Object} KpiValue
 * @property {number} kpi_id    catalog KPI number (see src/kpis/definitions.js)
 * @property {number|null} value     current period
 * @property {number|null} previous  previous period (for the trend arrow)
 */

/**
 * Kafka topic fleet.silver.telemetry.v1: the catalog columns (Notion_Data_Catalog.md 3.14) + the silver columns.
 * The backend sends the row as it is; the silver topic also has event_timestamp, speed_kmh, stream_latency_sec,
 * dt, hr, updated_at (not used by the dashboard) and has no ingest_ts.
 * @typedef {Object} TelemetryRow
 * @property {string} vehicle_id
 * @property {string} device_id
 * @property {string} event_id
 * @property {string} event_ts
 * @property {number} source_sequence
 * @property {number|null} lat
 * @property {number|null} lon
 * @property {number|null} speed_mph
 * @property {number} heading_deg
 * @property {number} rpm
 * @property {number} engine_temp_f
 * @property {number} fuel_gph
 * @property {number} fuel_level_gal
 * @property {number} odometer_mi
 * @property {boolean} engine_on
 * @property {'DRIVING'|'PARKED'|'IDLING'} motion_status
 * @property {boolean} is_speeding
 * @property {boolean} is_engine_overheating
 * @property {boolean} is_low_fuel
 * @property {boolean} is_idling             same as motion_status = IDLING (idle now, not "over 30 min")
 */

/**
 * Kafka topic fleet.silver.reefer.v1: the catalog columns (Notion_Data_Catalog.md 3.15) + the silver columns
 * (also event_timestamp, dt, hr, updated_at, not used; no ingest_ts).
 * @typedef {Object} ReeferRow
 * @property {string} vehicle_id
 * @property {string} trailer_id
 * @property {string} sensor_id
 * @property {string} event_id
 * @property {string} event_ts
 * @property {number|null} cargo_temp_f
 * @property {number} setpoint_f
 * @property {boolean} compressor_on
 * @property {boolean} door_open
 * @property {number} ambient_temp_f
 * @property {number} reefer_fuel_gph
 * @property {string} unit_mode
 * @property {'Pharma'|'Chilled'|'Frozen'} commodity_type
 * @property {number} allowed_temp_min_f
 * @property {number} allowed_temp_max_f
 * @property {boolean} is_temp_breach
 * @property {boolean} is_reefer_unit_failure
 */

/**
 * An alert made by the backend from the latest row's flags. Same names as gen_anomaly_labels (3.16).
 * Flag alerts are active while the flag is true: is_speeding -> SPEEDING, is_engine_overheating -> ENGINE_OVERHEATING,
 * is_low_fuel -> LOW_FUEL, is_temp_breach -> COLD_CHAIN_BREACH, is_reefer_unit_failure -> REEFER_UNIT_FAILURE.
 * EXCESSIVE_IDLING starts after 30 min of is_idling (by event_ts), with start_ts = the first idle row.
 * ROUTE_DEVIATION has no flag in the stream yet: the backend never sends it (kept for a future flag).
 * @typedef {Object} AlertRow
 * @property {string} anomaly_id   real backend: vehicle_id-anomaly_type-start_ts (same id after a backend restart)
 * @property {'EXCESSIVE_IDLING'|'ROUTE_DEVIATION'|'REEFER_UNIT_FAILURE'|'COLD_CHAIN_BREACH'|'SPEEDING'|'ENGINE_OVERHEATING'|'LOW_FUEL'} anomaly_type
 * @property {string} vehicle_id
 * @property {string|null} trip_id   null from the real backend (not in the stream)
 * @property {string} start_ts
 * @property {string|null} end_ts   null while the alert is still active
 */

/**
 * Live KPIs calculated by the backend from the latest row of each truck kept. Counts are trucks, % are percent.
 * @typedef {Object} LiveKpis
 * @property {string} as_of                       backend time (UTC) of the calculation
 * @property {number} trucks_reporting            trucks with a telemetry row
 * @property {Object<string, number>} motion_status  trucks per motion_status
 * @property {number} is_speeding                 trucks with the flag now (same for the next two)
 * @property {number} is_engine_overheating
 * @property {number} is_low_fuel
 * @property {number} reefers_reporting           trucks with a reefer row
 * @property {number} is_reefer_unit_failure
 * @property {number|null} cold_chain_compliance_pct   valid readings (cargo_temp_f not null) without is_temp_breach
 * @property {Object<string, number>} cold_chain_compliance_pct_by_commodity
 * @property {string|null} newest_event_ts
 * @property {number|null} data_age_min           as_of - newest_event_ts
 * @property {string|null} last_received_at       backend time (UTC) when the last new row arrived
 */

/**
 * Catalog KPIs and charts calculated by the backend from EVERY Kafka row of the window (backend/app/services/stream_kpis.py).
 * Window = last STREAM_HISTORY_MINUTES (60) of event_ts, ending at the newest row; previous = the 60 min before.
 * Kafka has no trip_id / load_id: one trailer (reefer) or truck (telemetry) inside the window counts as one trip.
 * Same shapes as DashboardResponse, where these are null; units as in src/kpis/definitions.js.
 * @typedef {Object} StreamKpis
 * @property {string} period       e.g. "60 min to 14:55 vs previous 60 min"
 * @property {KpiValue[]} kpis     KPIs 10, 11, 12, 13, 14, 15, 16, 23, 29, 33, 34 (rows, event_ts window) and platform KPIs
 *   54, 57, 58 (Kafka messages, last 60 min of Kafka time vs the 60 before) and 60 (now - newest Kafka time, no previous)
 * @property {Object<string, any>} series  trip_temperature (object or null, trip_id null), excursions_by_trailer,
 *   excursion_rate_by_ambient (kpi_17 per band), high_risk_trips (trip_id null), time_in_state (state = motion_status)
 */

export {}
