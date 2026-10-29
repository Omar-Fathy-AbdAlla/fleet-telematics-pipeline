-- KPI 42 Maintenance Downtime (h): sum of maintenance downtime_hours. Period date: MAINTENANCE_DATE.
SELECT
    IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(downtime_hours)                                               AS kpi_value
FROM fct_maintenance
WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
