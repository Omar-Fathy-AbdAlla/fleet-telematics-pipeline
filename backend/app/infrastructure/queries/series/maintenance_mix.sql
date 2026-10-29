-- Chart maintenance_mix (Maintenance): order count and total_cost (USD) per maintenance_type, current period.
SELECT
    maintenance_type,
    COUNT(*)          AS orders,
    SUM(total_cost)   AS total_cost
FROM fct_maintenance
WHERE maintenance_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY maintenance_type
ORDER BY total_cost DESC
