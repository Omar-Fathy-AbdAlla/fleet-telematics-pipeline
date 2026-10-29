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
