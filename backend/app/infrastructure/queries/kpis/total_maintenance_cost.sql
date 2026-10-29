-- KPI 41 Total Maintenance Cost (USD): sum of maintenance total_cost (labor_cost + parts_cost). Period date: MAINTENANCE_DATE.
SELECT
    IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(total_cost)                                                   AS kpi_value
FROM fct_maintenance
WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
