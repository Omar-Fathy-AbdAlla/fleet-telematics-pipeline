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
