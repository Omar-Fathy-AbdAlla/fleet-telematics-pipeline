-- Chart cost_trend (Maintenance): monthly labor_cost and parts_cost (USD), 12 months up to current_end.
SELECT
    TO_CHAR(DATE_TRUNC('month', maintenance_date), 'YYYY-MM')   AS month,
    SUM(labor_cost)                                             AS labor_cost,
    SUM(parts_cost)                                             AS parts_cost
FROM fct_maintenance
WHERE maintenance_date BETWEEN DATEADD('month', -11, DATE_TRUNC('month', %(current_end)s::DATE)) AND %(current_end)s
GROUP BY month
ORDER BY month
