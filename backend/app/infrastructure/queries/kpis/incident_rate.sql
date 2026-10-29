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
