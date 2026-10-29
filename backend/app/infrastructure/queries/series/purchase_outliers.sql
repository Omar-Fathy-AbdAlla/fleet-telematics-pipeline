-- Chart purchase_outliers (Fuel): the 8 purchases with the highest KPI 22 Fuel Price Variance (pct), current period.
-- Same rule as kpis/fuel_price_variance.sql (reference = national diesel price of the purchase day, USD/L).
WITH diesel AS (
    SELECT
        TRY_TO_DATE(effective_date)                              AS price_date,
        TRY_TO_DECIMAL(price_per_gallon, 10, 4) / 3.78541        AS reference_price_per_liter
    FROM raw_data.diesel_prices
)
SELECT
    f.fuel_purchase_id,
    f.truck_id,
    f.location_state,
    f.liters,
    f.price_per_liter,
    f.total_cost,
    (f.price_per_liter - d.reference_price_per_liter) / d.reference_price_per_liter * 100   AS kpi_22
FROM fct_fuel_purchases f
JOIN diesel d ON d.price_date = f.purchase_date
WHERE f.purchase_date BETWEEN %(current_start)s AND %(current_end)s
ORDER BY kpi_22 DESC
LIMIT 8
