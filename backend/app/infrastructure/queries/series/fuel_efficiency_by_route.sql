-- Chart fuel_efficiency_by_route (Fuel): KPI 21 Fuel Efficiency (L/100km) and KPI 20 Fuel Cost per km (USD/km) per route,
-- current period, least efficient first (highest L/100km). Same rules as kpis/fuel_efficiency.sql and kpis/fuel_cost_per_km.sql.
WITH fuel_price AS (
    SELECT SUM(total_cost) / SUM(liters)                               AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(current_start)s AND %(current_end)s
)
SELECT
    r.route_id,
    o.city                                                             AS origin_city,
    d.city                                                             AS destination_city,
    AVG(t.average_l_per_100km)                                         AS kpi_21,
    SUM(t.fuel_liters_used) * p.price_per_liter / SUM(t.actual_distance_km)   AS kpi_20
FROM fct_trips t
JOIN dim_route r    ON r.route_key = t.route_key
JOIN dim_location o ON o.location_key = r.origin_location_key
JOIN dim_location d ON d.location_key = r.destination_location_key
CROSS JOIN fuel_price p
WHERE t.arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
GROUP BY r.route_id, o.city, d.city, p.price_per_liter
ORDER BY kpi_21 DESC
