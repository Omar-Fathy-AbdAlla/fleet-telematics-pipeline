-- KPI 22 Fuel Price Variance (pct): average over purchases of (price_per_liter - reference) / reference x 100.
-- reference = national diesel price of the purchase day, from RAW_DATA.DIESEL_PRICES (not in DBT_MARTS yet; text columns,
-- USD per gallon, converted to USD per liter with 1 gal = 3.78541 L).
-- Period date: PURCHASE_DATE.
WITH diesel AS (
    SELECT
        TRY_TO_DATE(effective_date)                              AS price_date,
        TRY_TO_DECIMAL(price_per_gallon, 10, 4) / 3.78541        AS reference_price_per_liter
    FROM raw_data.diesel_prices
)
SELECT
    IFF(f.purchase_date >= %(current_start)s, 'value', 'previous')                                  AS period,
    AVG((f.price_per_liter - d.reference_price_per_liter) / d.reference_price_per_liter * 100)     AS kpi_value
FROM fct_fuel_purchases f
JOIN diesel d ON d.price_date = f.purchase_date
WHERE f.purchase_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
