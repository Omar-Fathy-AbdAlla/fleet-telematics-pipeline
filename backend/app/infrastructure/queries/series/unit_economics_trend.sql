-- Chart unit_economics_trend (Executive): weekly KPI 26 Revenue per km and KPI 20 Fuel Cost per km (USD/km),
-- 12 weeks up to current_end. Same rules as kpis/revenue_per_km.sql and kpis/fuel_cost_per_km.sql, with the week's fuel price.
WITH fuel_price AS (
    SELECT
        DATE_TRUNC('week', purchase_date)                                   AS week_start,
        SUM(total_cost) / SUM(liters)                                       AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
    GROUP BY week_start
),
trip_totals AS (
    SELECT
        DATE_TRUNC('week', arrival_ts::DATE)                                       AS week_start,
        SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd)     AS revenue,
        SUM(fuel_liters_used)                                               AS liters_used,
        SUM(actual_distance_km)                                             AS distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
    GROUP BY week_start
)
SELECT
    t.week_start,
    t.revenue / t.distance_km                                               AS kpi_26,
    t.liters_used * p.price_per_liter / t.distance_km                       AS kpi_20
FROM trip_totals t
JOIN fuel_price p ON p.week_start = t.week_start
ORDER BY t.week_start
