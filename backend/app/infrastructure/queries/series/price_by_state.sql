-- Chart price_by_state (Fuel): average price paid per liter by state (USD/L) vs the national reference diesel price (USD/L),
-- current period. Reference = average of RAW_DATA.DIESEL_PRICES in the period (USD per gallon / 3.78541), as in kpis/fuel_price_variance.sql.
WITH reference AS (
    SELECT AVG(TRY_TO_DECIMAL(price_per_gallon, 10, 4) / 3.78541)    AS reference_price_per_liter
    FROM raw_data.diesel_prices
    WHERE TRY_TO_DATE(effective_date) BETWEEN %(current_start)s AND %(current_end)s
)
SELECT
    f.location_state,
    SUM(f.total_cost) / SUM(f.liters)                                AS price_per_liter,
    r.reference_price_per_liter
FROM fct_fuel_purchases f
CROSS JOIN reference r
WHERE f.purchase_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY f.location_state, r.reference_price_per_liter
ORDER BY price_per_liter DESC
