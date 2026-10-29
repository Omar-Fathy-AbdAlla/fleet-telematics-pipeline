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
