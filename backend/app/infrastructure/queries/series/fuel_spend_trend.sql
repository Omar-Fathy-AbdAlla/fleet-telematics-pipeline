-- Chart fuel_spend_trend (Fuel): weekly sum of fuel purchase total_cost (USD), 12 weeks up to current_end.
SELECT
    DATE_TRUNC('week', purchase_date)   AS week_start,
    SUM(total_cost)                     AS total_cost
FROM fct_fuel_purchases
WHERE purchase_date BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
GROUP BY week_start
ORDER BY week_start
