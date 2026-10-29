-- KPI 19 Total Fuel Spend (USD): sum of fuel purchase total_cost (bought, not burned). Period date: PURCHASE_DATE.
SELECT
    IFF(purchase_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(total_cost)                                                AS kpi_value
FROM fct_fuel_purchases
WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
