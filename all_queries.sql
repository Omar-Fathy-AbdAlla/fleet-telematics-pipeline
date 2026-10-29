-- All backend SQL queries merged (source: backend/app/infrastructure/queries)
-- Each section starts with the original file path.

-- ============================================================
-- KPIS
-- ============================================================

-- ------------------------------------------------------------
-- FILE: kpis/average_delivery_delay.sql
-- ------------------------------------------------------------
-- KPI 3 Average Delivery Delay (min): average delay_minutes of late deliveries only (delay_minutes > 0).
-- Early deliveries (negative delay) are excluded so they do not cancel out late ones. Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    AVG(delay_minutes)                                           AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND delay_minutes > 0
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/claim_cost.sql
-- ------------------------------------------------------------
-- KPI 38 Claim Cost (USD): sum of safety incident claim_amount. Period date: INCIDENT_DATE.
SELECT
    IFF(incident_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(claim_amount)                                              AS kpi_value
FROM fct_safety_incidents
WHERE incident_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/destination_queue_time.sql
-- ------------------------------------------------------------
-- KPI 6 Destination Queue Time (min): average of delivery actual_datetime - trip arrival_ts.
-- Join: FCT_DELIVERY_EVENTS -> FCT_TRIPS on TRIP_ID (events of trips not completed yet have no match). Period date: ACTUAL_DATE.
SELECT
    IFF(e.actual_date >= %(current_start)s, 'value', 'previous')     AS period,
    AVG(DATEDIFF('minute', t.arrival_ts, e.actual_datetime))         AS kpi_value
FROM fct_delivery_events e
JOIN fct_trips t ON t.trip_id = e.trip_id
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/dock_time.sql
-- ------------------------------------------------------------
-- KPI 7 Dock Time (min): average detention_minutes of pickup and delivery events (loading / unloading time).
-- Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    AVG(detention_minutes)                                       AS kpi_value
FROM fct_delivery_events
WHERE actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/fuel_cost_pct_of_revenue.sql
-- ------------------------------------------------------------
-- KPI 27 Fuel Cost of Revenue (pct): trips' fuel cost / trips' total load revenue x 100.
-- fuel cost = fuel_liters_used x the period's average price per liter (consumption-based, same rule as KPI 20).
-- revenue   = revenue_usd + fuel_surcharge_usd + accessorial_charges_usd.
-- Period date: ARRIVAL_TS date (day the trip finished) for trips, PURCHASE_DATE for purchases.
WITH fuel_price AS (
    SELECT
        IFF(purchase_date >= %(current_start)s, 'value', 'previous')                AS period,
        SUM(total_cost) / SUM(liters)                                               AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
trip_totals AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')                    AS period,
        SUM(fuel_liters_used)                                                       AS liters_used,
        SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd)             AS revenue
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    t.period,
    t.liters_used * p.price_per_liter / t.revenue * 100                             AS kpi_value
FROM trip_totals t
JOIN fuel_price p ON p.period = t.period


-- ------------------------------------------------------------
-- FILE: kpis/fuel_cost_per_km.sql
-- ------------------------------------------------------------
-- KPI 20 Fuel Cost per km (USD/km), consumption-based:
-- trips' fuel_liters_used x the period's average price per liter / trips' km.
-- average price per liter = SUM(total_cost) / SUM(liters) of the period's fuel purchases.
-- Period date: ARRIVAL_TS date (day the trip finished) for trips, PURCHASE_DATE for purchases.
WITH fuel_price AS (
    SELECT
        IFF(purchase_date >= %(current_start)s, 'value', 'previous')   AS period,
        SUM(total_cost) / SUM(liters)                                  AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
trip_totals AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')       AS period,
        SUM(fuel_liters_used)                                          AS liters_used,
        SUM(actual_distance_km)                                        AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    t.period,
    t.liters_used * p.price_per_liter / t.distance_km                  AS kpi_value
FROM trip_totals t
JOIN fuel_price p ON p.period = t.period


-- ------------------------------------------------------------
-- FILE: kpis/fuel_efficiency.sql
-- ------------------------------------------------------------
-- KPI 21 Fuel Efficiency (L/100km): average of FCT_TRIPS.average_l_per_100km, as the data gives it. Lower is better.
-- Period date: ARRIVAL_TS date (day the trip finished).
SELECT
    IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')   AS period,
    AVG(average_l_per_100km)                                   AS kpi_value
FROM fct_trips
WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/fuel_price_variance.sql
-- ------------------------------------------------------------
-- KPI 22 Fuel Price Variance (pct): average over purchases of (price_per_liter - reference) / reference x 100.
-- reference = national diesel price of the purchase day, from RAW_DATA.DIESEL_PRICES (not in DBT_MARTS yet; text columns,
-- USD per gallon, converted to USD per liter with 1 gal = 3.78541 L).
-- Period date: PURCHASE_DATE.
WITH diesel AS (
    SELECT
        TRY_TO_DATE(effective_date)                              AS price_date,
        TRY_TO_DECIMAL(price_per_gallon, 10, 4) / 3.78541        AS reference_price_per_liter
    FROM raw_data.diesel_prices
)
SELECT
    IFF(f.purchase_date >= %(current_start)s, 'value', 'previous')                                  AS period,
    AVG((f.price_per_liter - d.reference_price_per_liter) / d.reference_price_per_liter * 100)     AS kpi_value
FROM fct_fuel_purchases f
JOIN diesel d ON d.price_date = f.purchase_date
WHERE f.purchase_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/idle_time_share.sql
-- ------------------------------------------------------------
-- KPI 24 Idle Time Share (pct): SUM(idle_time_hours) / SUM(actual_duration_hours) x 100 over trips. Period date: ARRIVAL_TS date (day the trip finished).
SELECT
    IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')     AS period,
    SUM(idle_time_hours) / SUM(actual_duration_hours) * 100      AS kpi_value
FROM fct_trips
WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/incident_rate.sql
-- ------------------------------------------------------------
-- KPI 36 Incident Rate (per 1M km): COUNT(safety incidents) / SUM(trips' actual_distance_km) x 1,000,000.
-- Period date: INCIDENT_DATE for incidents, ARRIVAL_TS date (day the trip finished) for trips.
WITH incidents AS (
    SELECT
        IFF(incident_date >= %(current_start)s, 'value', 'previous')   AS period,
        COUNT(*)                                                       AS incidents
    FROM fct_safety_incidents
    WHERE incident_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
trip_km AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')       AS period,
        SUM(actual_distance_km)                                        AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    k.period,
    COALESCE(i.incidents, 0) * 1000000 / k.distance_km                 AS kpi_value   -- multiply first: Snowflake keeps 6 decimals in a division
FROM trip_km k
LEFT JOIN incidents i ON i.period = k.period


-- ------------------------------------------------------------
-- FILE: kpis/km_per_truck_per_day.sql
-- ------------------------------------------------------------
-- KPI 30 Km per Truck per Day (km): SUM(trips' actual_distance_km) / (trucks x days).
-- trucks x days = number of FCT_TRUCK_DAILY rows in the period (one row per fleet truck per day, ~5,000 per day).
-- Period date: ARRIVAL_TS date (day the trip finished) for trips, snapshot date (DIM_DATE.FULL_DATE) for truck days.
WITH trip_km AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')     AS period,
        SUM(actual_distance_km)                                      AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
truck_days AS (
    SELECT
        IFF(d.full_date >= %(current_start)s, 'value', 'previous')   AS period,
        COUNT(*)                                                     AS truck_days
    FROM fct_truck_daily f
    JOIN dim_date d ON d.date_key = f.snapshot_date_key
    WHERE d.full_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    k.period,
    k.distance_km / d.truck_days                                     AS kpi_value
FROM trip_km k
JOIN truck_days d ON d.period = k.period


-- ------------------------------------------------------------
-- FILE: kpis/maintenance_cost_per_km.sql
-- ------------------------------------------------------------
-- KPI 44 Maintenance Cost per km (USD/km): SUM(maintenance total_cost) / SUM(trips' actual_distance_km) in the same period.
-- Period date: MAINTENANCE_DATE for maintenance, ARRIVAL_TS date (day the trip finished) for trips.
WITH maintenance AS (
    SELECT
        IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
        SUM(total_cost)                                                   AS maintenance_cost
    FROM fct_maintenance
    WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
trip_km AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')          AS period,
        SUM(actual_distance_km)                                           AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    k.period,
    COALESCE(m.maintenance_cost, 0) / k.distance_km                       AS kpi_value
FROM trip_km k
LEFT JOIN maintenance m ON m.period = k.period


-- ------------------------------------------------------------
-- FILE: kpis/maintenance_downtime.sql
-- ------------------------------------------------------------
-- KPI 42 Maintenance Downtime (h): sum of maintenance downtime_hours. Period date: MAINTENANCE_DATE.
SELECT
    IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(downtime_hours)                                               AS kpi_value
FROM fct_maintenance
WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/margin_proxy.sql
-- ------------------------------------------------------------
-- KPI 28 Margin Proxy per Trip (USD): average over trips of revenue - fuel cost - allocated maintenance cost.
-- revenue     = revenue_usd + fuel_surcharge_usd + accessorial_charges_usd
-- fuel cost   = fuel_liters_used x the period's average price per liter (consumption-based, same rule as KPI 20)
-- maintenance = truck's maintenance total_cost in the period x trip km / truck's trip km in the period
-- Trips without TRUCK_KEY are excluded (maintenance cannot be allocated). A proxy, not profit.
-- Period date: ARRIVAL_TS date (day the trip finished) for trips, PURCHASE_DATE for purchases, MAINTENANCE_DATE for maintenance.
WITH fuel_price AS (
    SELECT
        IFF(purchase_date >= %(current_start)s, 'value', 'previous')       AS period,
        SUM(total_cost) / SUM(liters)                                      AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
truck_maintenance AS (
    SELECT
        IFF(maintenance_date >= %(current_start)s, 'value', 'previous')    AS period,
        truck_key,
        SUM(total_cost)                                                    AS maintenance_cost
    FROM fct_maintenance
    WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period, truck_key
),
trips AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')           AS period,
        truck_key,
        revenue_usd + fuel_surcharge_usd + accessorial_charges_usd         AS revenue,
        fuel_liters_used,
        actual_distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
      AND truck_key IS NOT NULL
),
trips_with_truck_km AS (
    SELECT *, SUM(actual_distance_km) OVER (PARTITION BY period, truck_key)   AS truck_distance_km
    FROM trips
)
SELECT
    t.period,
    AVG(t.revenue
        - t.fuel_liters_used * p.price_per_liter
        - COALESCE(m.maintenance_cost, 0) * t.actual_distance_km / t.truck_distance_km)   AS kpi_value
FROM trips_with_truck_km t
JOIN fuel_price p             ON p.period = t.period
LEFT JOIN truck_maintenance m  ON m.period = t.period AND m.truck_key = t.truck_key
GROUP BY t.period


-- ------------------------------------------------------------
-- FILE: kpis/on_time_delivery_rate.sql
-- ------------------------------------------------------------
-- KPI 1 On-Time Delivery Rate (pct): delivery events with on_time_flag TRUE / all delivery events x 100.
-- on_time_flag already includes the 15-min grace period. Period date: ACTUAL_DATE.
-- Every KPI query returns one row per period: PERIOD ('value' = current, 'previous') and KPI_VALUE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(on_time_flag = 'TRUE') / COUNT(*) * 100             AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/on_time_pickup_rate.sql
-- ------------------------------------------------------------
-- KPI 2 On-Time Pickup Rate (pct): pickup events with on_time_flag TRUE / all pickup events x 100.
-- on_time_flag already includes the 15-min grace period. Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(on_time_flag = 'TRUE') / COUNT(*) * 100             AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'PICKUP'
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/orders_per_truck.sql
-- ------------------------------------------------------------
-- KPI 43 Orders per Truck (orders): COUNT(maintenance orders) / fleet trucks, per 30-day period (not annualised).
-- fleet trucks = distinct TRUCK_KEY in FCT_TRUCK_DAILY in the period.
-- Period date: MAINTENANCE_DATE for orders, snapshot date (DIM_DATE.FULL_DATE) for trucks.
WITH orders AS (
    SELECT
        IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
        COUNT(*)                                                          AS orders
    FROM fct_maintenance
    WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
fleet AS (
    SELECT
        IFF(d.full_date >= %(current_start)s, 'value', 'previous')        AS period,
        COUNT(DISTINCT f.truck_key)                                       AS trucks
    FROM fct_truck_daily f
    JOIN dim_date d ON d.date_key = f.snapshot_date_key
    WHERE d.full_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    f.period,
    COALESCE(o.orders, 0) / f.trucks                                      AS kpi_value
FROM fleet f
LEFT JOIN orders o ON o.period = f.period


-- ------------------------------------------------------------
-- FILE: kpis/revenue_per_km.sql
-- ------------------------------------------------------------
-- KPI 26 Revenue per km (USD/km): SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / SUM(actual_distance_km).
-- Period date: ARRIVAL_TS date (day the trip finished).
SELECT
    IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')                                     AS period,
    SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / SUM(actual_distance_km)    AS kpi_value
FROM fct_trips
WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/severe_delay_rate.sql
-- ------------------------------------------------------------
-- KPI 5 Severe Delay Rate (pct): delivery events with delay_minutes > 120 / all delivery events x 100.
-- 120 min is an assumption (catalog: the team picks the threshold). Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(delay_minutes > 120) / COUNT(*) * 100               AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/total_fuel_spend.sql
-- ------------------------------------------------------------
-- KPI 19 Total Fuel Spend (USD): sum of fuel purchase total_cost (bought, not burned). Period date: PURCHASE_DATE.
SELECT
    IFF(purchase_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(total_cost)                                                AS kpi_value
FROM fct_fuel_purchases
WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/total_maintenance_cost.sql
-- ------------------------------------------------------------
-- KPI 41 Total Maintenance Cost (USD): sum of maintenance total_cost (labor_cost + parts_cost). Period date: MAINTENANCE_DATE.
SELECT
    IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(total_cost)                                                   AS kpi_value
FROM fct_maintenance
WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/trip_duration_variance.sql
-- ------------------------------------------------------------
-- KPI 8 Trip Duration Variance (pct): average over trips of (actual - planned) / planned x 100.
-- planned hours = scheduled DELIVERY datetime - scheduled PICKUP datetime of the trip (FCT_DELIVERY_EVENTS).
-- actual hours  = FCT_TRIPS.actual_duration_hours. Trips missing one of the two events give NULL and are skipped by AVG.
-- Period date: ARRIVAL_TS date (day the trip finished).
WITH trip_schedule AS (
    SELECT
        trip_id,
        DATEDIFF('minute',
                 MAX(IFF(event_type = 'PICKUP', scheduled_datetime, NULL)),
                 MAX(IFF(event_type = 'DELIVERY', scheduled_datetime, NULL))) / 60      AS planned_hours
    FROM fct_delivery_events
    GROUP BY trip_id
)
SELECT
    IFF(t.arrival_ts::DATE >= %(current_start)s, 'value', 'previous')                          AS period,
    AVG((t.actual_duration_hours - s.planned_hours) / NULLIF(s.planned_hours, 0) * 100)  AS kpi_value
FROM fct_trips t
JOIN trip_schedule s ON s.trip_id = t.trip_id
WHERE t.arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/truck_availability.sql
-- ------------------------------------------------------------
-- KPI 46 Truck Availability (pct): truck-days not in maintenance / all truck-days x 100.
-- In maintenance = FCT_TRUCK_DAILY.is_in_maintenance (chosen over truck_status: the two columns disagree).
-- Period date: snapshot date (DIM_DATE.FULL_DATE).
SELECT
    IFF(d.full_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(NOT f.is_in_maintenance) / COUNT(*) * 100           AS kpi_value
FROM fct_truck_daily f
JOIN dim_date d ON d.date_key = f.snapshot_date_key
WHERE d.full_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period


-- ------------------------------------------------------------
-- FILE: kpis/warehouse_data_freshness.sql
-- ------------------------------------------------------------
-- KPI 65 Warehouse Data Freshness (min): now - the newest Airbyte load (_AIRBYTE_EXTRACTED_AT) over the 13 RAW_DATA tables.
-- A point in time, not a period: only 'value' (previous stays null). The period parameters are not used.
SELECT
    'value'                                                                   AS period,
    ROUND(DATEDIFF('second', MAX(loaded_at), CURRENT_TIMESTAMP()) / 60, 1)   AS kpi_value
FROM (
    SELECT MAX(_airbyte_extracted_at) AS loaded_at FROM raw_data.customers
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.delivery_events
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.diesel_prices
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.drivers
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.facilities
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.fuel_purchases
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.loads
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.maintenance_records
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.routes
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.safety_incidents
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.trailers
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.trips
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.trucks
)


-- ============================================================
-- SERIES
-- ============================================================

-- ------------------------------------------------------------
-- FILE: series/cost_by_model_year.sql
-- ------------------------------------------------------------
-- Chart cost_by_model_year (Maintenance): KPI 44 Maintenance Cost per km (USD/km) per truck model_year, current period.
-- Per model year: SUM(maintenance total_cost) / SUM(trips' actual_distance_km) of its trucks. Same rule as kpis/maintenance_cost_per_km.sql.
WITH maintenance AS (
    SELECT tr.model_year, SUM(m.total_cost)         AS maintenance_cost
    FROM fct_maintenance m
    JOIN dim_truck tr ON tr.truck_key = m.truck_key
    WHERE m.maintenance_date BETWEEN %(current_start)s AND %(current_end)s
    GROUP BY tr.model_year
),
trip_km AS (
    SELECT tr.model_year, SUM(t.actual_distance_km) AS distance_km
    FROM fct_trips t
    JOIN dim_truck tr ON tr.truck_key = t.truck_key
    WHERE t.arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
    GROUP BY tr.model_year
)
SELECT
    k.model_year,
    COALESCE(m.maintenance_cost, 0) / k.distance_km   AS kpi_44
FROM trip_km k
LEFT JOIN maintenance m ON m.model_year = k.model_year
ORDER BY k.model_year


-- ------------------------------------------------------------
-- FILE: series/cost_trend.sql
-- ------------------------------------------------------------
-- Chart cost_trend (Maintenance): monthly labor_cost and parts_cost (USD), 12 months up to current_end.
SELECT
    TO_CHAR(DATE_TRUNC('month', maintenance_date), 'YYYY-MM')   AS month,
    SUM(labor_cost)                                             AS labor_cost,
    SUM(parts_cost)                                             AS parts_cost
FROM fct_maintenance
WHERE maintenance_date BETWEEN DATEADD('month', -11, DATE_TRUNC('month', %(current_end)s::DATE)) AND %(current_end)s
GROUP BY month
ORDER BY month


-- ------------------------------------------------------------
-- FILE: series/delay_by_hour.sql
-- ------------------------------------------------------------
-- Chart delay_by_hour (Delivery): KPI 3 Average Delivery Delay (min, late deliveries only) per scheduled hour
-- (Cairo time; scheduled_datetime is UTC), current period. Same rule as kpis/average_delivery_delay.sql.
SELECT
    TO_CHAR(CONVERT_TIMEZONE('UTC', 'Africa/Cairo', scheduled_datetime), 'HH24') || ':00'   AS hour,
    AVG(delay_minutes)                             AS kpi_3
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND delay_minutes > 0
  AND actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY hour
ORDER BY hour


-- ------------------------------------------------------------
-- FILE: series/driver_scorecard.sql
-- ------------------------------------------------------------
-- Chart driver_scorecard (Safety): the 10 drivers with the most safety incidents in the current period (then most km).
-- distance_km = SUM(trips' actual_distance_km), kpi_24 = Idle Time Share (pct), same rule as kpis/idle_time_share.sql.
-- DIM_DRIVER keeps history, so only the current row (is_current) is joined.
WITH driver_trips AS (
    SELECT
        driver_id,
        SUM(actual_distance_km)                                AS distance_km,
        SUM(idle_time_hours) / SUM(actual_duration_hours) * 100   AS kpi_24
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
      AND driver_id IS NOT NULL
    GROUP BY driver_id
),
driver_incidents AS (
    SELECT driver_id, COUNT(*)                                 AS incidents
    FROM fct_safety_incidents
    WHERE incident_date BETWEEN %(current_start)s AND %(current_end)s
    GROUP BY driver_id
)
SELECT
    t.driver_id,
    d.first_name,
    d.last_name,
    t.distance_km,
    t.kpi_24,
    COALESCE(i.incidents, 0)                                   AS incidents
FROM driver_trips t
JOIN dim_driver d            ON d.driver_id = t.driver_id AND d.is_current
LEFT JOIN driver_incidents i ON i.driver_id = t.driver_id
ORDER BY incidents DESC, t.distance_km DESC
LIMIT 10


-- ------------------------------------------------------------
-- FILE: series/facility_queue.sql
-- ------------------------------------------------------------
-- Chart facility_queue (Delivery): the 10 facilities with the longest KPI 6 Destination Queue Time (min), current period.
-- Same rule as kpis/destination_queue_time.sql.
SELECT
    f.facility_id,
    f.facility_name,
    l.city,
    AVG(DATEDIFF('minute', t.arrival_ts, e.actual_datetime))   AS kpi_6
FROM fct_delivery_events e
JOIN fct_trips t    ON t.trip_id = e.trip_id
JOIN dim_facility f ON f.facility_id = e.facility_id
JOIN dim_location l ON l.location_key = f.location_key
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY kpi_6 DESC
LIMIT 10


-- ------------------------------------------------------------
-- FILE: series/fuel_efficiency_by_route.sql
-- ------------------------------------------------------------
-- Chart fuel_efficiency_by_route (Fuel): KPI 21 Fuel Efficiency (L/100km) and KPI 20 Fuel Cost per km (USD/km) per route,
-- current period, least efficient first (highest L/100km). Same rules as kpis/fuel_efficiency.sql and kpis/fuel_cost_per_km.sql.
WITH fuel_price AS (
    SELECT SUM(total_cost) / SUM(liters)                               AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(current_start)s AND %(current_end)s
)
SELECT
    r.route_id,
    o.city                                                             AS origin_city,
    d.city                                                             AS destination_city,
    AVG(t.average_l_per_100km)                                         AS kpi_21,
    SUM(t.fuel_liters_used) * p.price_per_liter / SUM(t.actual_distance_km)   AS kpi_20
FROM fct_trips t
JOIN dim_route r    ON r.route_key = t.route_key
JOIN dim_location o ON o.location_key = r.origin_location_key
JOIN dim_location d ON d.location_key = r.destination_location_key
CROSS JOIN fuel_price p
WHERE t.arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
GROUP BY r.route_id, o.city, d.city, p.price_per_liter
ORDER BY kpi_21 DESC


-- ------------------------------------------------------------
-- FILE: series/fuel_efficiency_by_truck.sql
-- ------------------------------------------------------------
-- Chart fuel_efficiency_by_truck (Fuel): the 10 least fuel-efficient trucks by KPI 21 Fuel Efficiency (L/100km, highest first),
-- current period. Trips without TRUCK_KEY are left out.
SELECT
    tr.truck_id,
    tr.make,
    AVG(t.average_l_per_100km)   AS kpi_21
FROM fct_trips t
JOIN dim_truck tr ON tr.truck_key = t.truck_key
WHERE t.arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY kpi_21 DESC
LIMIT 10


-- ------------------------------------------------------------
-- FILE: series/fuel_spend_trend.sql
-- ------------------------------------------------------------
-- Chart fuel_spend_trend (Fuel): weekly sum of fuel purchase total_cost (USD), 12 weeks up to current_end.
SELECT
    DATE_TRUNC('week', purchase_date)   AS week_start,
    SUM(total_cost)                     AS total_cost
FROM fct_fuel_purchases
WHERE purchase_date BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
GROUP BY week_start
ORDER BY week_start


-- ------------------------------------------------------------
-- FILE: series/incidents_by_type.sql
-- ------------------------------------------------------------
-- Chart incidents_by_type (Safety): incident count and total claim_amount (USD) per incident_type, current period.
SELECT
    incident_type,
    COUNT(*)            AS incidents,
    SUM(claim_amount)   AS claim_amount
FROM fct_safety_incidents
WHERE incident_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY incident_type
ORDER BY claim_amount DESC


-- ------------------------------------------------------------
-- FILE: series/lane_otd.sql
-- ------------------------------------------------------------
-- Chart lane_otd (Delivery lane map + heatmap): KPI 1 On-Time Delivery Rate (pct) and delivery count per route,
-- current period. Coordinates come from DIM_LOCATION (origin and destination city) to draw the lane on the map.
SELECT
    r.route_id,
    o.city                                                 AS origin_city,
    o.state_code                                           AS origin_state,
    d.city                                                 AS destination_city,
    d.state_code                                           AS destination_state,
    r.typical_distance_km,
    o.latitude                                             AS origin_latitude,
    o.longitude                                            AS origin_longitude,
    d.latitude                                             AS destination_latitude,
    d.longitude                                            AS destination_longitude,
    COUNT(*)                                               AS deliveries,
    COUNT_IF(e.on_time_flag = 'TRUE') / COUNT(*) * 100     AS kpi_1
FROM fct_delivery_events e
JOIN dim_route r    ON r.route_id = e.route_id
JOIN dim_location o ON o.location_key = r.origin_location_key
JOIN dim_location d ON d.location_key = r.destination_location_key
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY r.route_id


-- ------------------------------------------------------------
-- FILE: series/maintenance_mix.sql
-- ------------------------------------------------------------
-- Chart maintenance_mix (Maintenance): order count and total_cost (USD) per maintenance_type, current period.
SELECT
    maintenance_type,
    COUNT(*)          AS orders,
    SUM(total_cost)   AS total_cost
FROM fct_maintenance
WHERE maintenance_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY maintenance_type
ORDER BY total_cost DESC


-- ------------------------------------------------------------
-- FILE: series/price_by_state.sql
-- ------------------------------------------------------------
-- Chart price_by_state (Fuel): average price paid per liter by state (USD/L) vs the national reference diesel price (USD/L),
-- current period. Reference = average of RAW_DATA.DIESEL_PRICES in the period (USD per gallon / 3.78541), as in kpis/fuel_price_variance.sql.
WITH reference AS (
    SELECT AVG(TRY_TO_DECIMAL(price_per_gallon, 10, 4) / 3.78541)    AS reference_price_per_liter
    FROM raw_data.diesel_prices
    WHERE TRY_TO_DATE(effective_date) BETWEEN %(current_start)s AND %(current_end)s
)
SELECT
    f.location_state,
    SUM(f.total_cost) / SUM(f.liters)                                AS price_per_liter,
    r.reference_price_per_liter
FROM fct_fuel_purchases f
CROSS JOIN reference r
WHERE f.purchase_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY f.location_state, r.reference_price_per_liter
ORDER BY price_per_liter DESC


-- ------------------------------------------------------------
-- FILE: series/purchase_outliers.sql
-- ------------------------------------------------------------
-- Chart purchase_outliers (Fuel): the 8 purchases with the highest KPI 22 Fuel Price Variance (pct), current period.
-- Same rule as kpis/fuel_price_variance.sql (reference = national diesel price of the purchase day, USD/L).
WITH diesel AS (
    SELECT
        TRY_TO_DATE(effective_date)                              AS price_date,
        TRY_TO_DECIMAL(price_per_gallon, 10, 4) / 3.78541        AS reference_price_per_liter
    FROM raw_data.diesel_prices
)
SELECT
    f.fuel_purchase_id,
    f.truck_id,
    f.location_state,
    f.liters,
    f.price_per_liter,
    f.total_cost,
    (f.price_per_liter - d.reference_price_per_liter) / d.reference_price_per_liter * 100   AS kpi_22
FROM fct_fuel_purchases f
JOIN diesel d ON d.price_date = f.purchase_date
WHERE f.purchase_date BETWEEN %(current_start)s AND %(current_end)s
ORDER BY kpi_22 DESC
LIMIT 8


-- ------------------------------------------------------------
-- FILE: series/repeat_trucks.sql
-- ------------------------------------------------------------
-- Chart repeat_trucks (Maintenance): the 10 trucks with the most maintenance orders in the current period (then highest cost),
-- with total_cost (USD) and downtime_hours (h).
SELECT
    m.truck_id,
    tr.make,
    COUNT(*)              AS orders,
    SUM(m.total_cost)     AS total_cost,
    SUM(m.downtime_hours) AS downtime_hours
FROM fct_maintenance m
JOIN dim_truck tr ON tr.truck_key = m.truck_key
WHERE m.maintenance_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY orders DESC, total_cost DESC
LIMIT 10


-- ------------------------------------------------------------
-- FILE: series/service_trend.sql
-- ------------------------------------------------------------
-- Chart service_trend (Executive): weekly KPI 1 On-Time Delivery Rate (pct), 12 weeks up to current_end.
SELECT
    DATE_TRUNC('week', actual_date)                    AS week_start,
    COUNT_IF(on_time_flag = 'TRUE') / COUNT(*) * 100   AS kpi_1
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND actual_date BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
GROUP BY week_start
ORDER BY week_start


-- ------------------------------------------------------------
-- FILE: series/unit_economics_trend.sql
-- ------------------------------------------------------------
-- Chart unit_economics_trend (Executive): weekly KPI 26 Revenue per km and KPI 20 Fuel Cost per km (USD/km),
-- 12 weeks up to current_end. Same rules as kpis/revenue_per_km.sql and kpis/fuel_cost_per_km.sql, with the week's fuel price.
WITH fuel_price AS (
    SELECT
        DATE_TRUNC('week', purchase_date)                                   AS week_start,
        SUM(total_cost) / SUM(liters)                                       AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
    GROUP BY week_start
),
trip_totals AS (
    SELECT
        DATE_TRUNC('week', arrival_ts::DATE)                                       AS week_start,
        SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd)     AS revenue,
        SUM(fuel_liters_used)                                               AS liters_used,
        SUM(actual_distance_km)                                             AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
    GROUP BY week_start
)
SELECT
    t.week_start,
    t.revenue / t.distance_km                                               AS kpi_26,
    t.liters_used * p.price_per_liter / t.distance_km                       AS kpi_20
FROM trip_totals t
JOIN fuel_price p ON p.week_start = t.week_start
ORDER BY t.week_start


-- ------------------------------------------------------------
-- FILE: series/worst_customers.sql
-- ------------------------------------------------------------
-- Chart worst_customers (Delivery): the 8 customers with the lowest KPI 1 On-Time Delivery Rate (pct), current period.
-- Customers with fewer than 10 deliveries are left out (assumption: too few to rank fairly).
-- DIM_CUSTOMER keeps history, so only the current row (is_current) is joined.
SELECT
    e.customer_id,
    c.customer_name,
    c.customer_type,
    COUNT(*)                                               AS deliveries,
    COUNT_IF(e.on_time_flag = 'TRUE') / COUNT(*) * 100     AS kpi_1
FROM fct_delivery_events e
JOIN dim_customer c ON c.customer_id = e.customer_id AND c.is_current
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
HAVING COUNT(*) >= 10
ORDER BY kpi_1, deliveries DESC
LIMIT 8

