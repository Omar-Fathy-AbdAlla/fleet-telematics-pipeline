-- KPI 20 Fuel Cost per km (USD/km), consumption-based:
-- trips' fuel_liters_used x the period's average price per liter / trips' km.
-- average price per liter = SUM(total_cost) / SUM(liters) of the period's fuel purchases.
-- Period date: ARRIVAL_TS date (day the trip finished) for trips, PURCHASE_DATE for purchases.
WITH fuel_price AS (
    SELECT
        IFF(purchase_date >= %(current_start)s, 'value', 'previous')   AS period,
        SUM(total_cost) / SUM(liters)                                  AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
trip_totals AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')       AS period,
        SUM(fuel_liters_used)                                          AS liters_used,
        SUM(actual_distance_km)                                        AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    t.period,
    t.liters_used * p.price_per_liter / t.distance_km                  AS kpi_value
FROM trip_totals t
JOIN fuel_price p ON p.period = t.period
