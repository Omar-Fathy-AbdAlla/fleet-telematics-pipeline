-- KPI 28 Margin Proxy per Trip (USD): average over trips of revenue - fuel cost - allocated maintenance cost.
-- revenue     = revenue_usd + fuel_surcharge_usd + accessorial_charges_usd
-- fuel cost   = fuel_liters_used x the period's average price per liter (consumption-based, same rule as KPI 20)
-- maintenance = truck's maintenance total_cost in the period x trip km / truck's trip km in the period
-- Trips without TRUCK_KEY are excluded (maintenance cannot be allocated). A proxy, not profit.
-- Period date: ARRIVAL_TS date (day the trip finished) for trips, PURCHASE_DATE for purchases, MAINTENANCE_DATE for maintenance.
WITH fuel_price AS (
    SELECT
        IFF(purchase_date >= %(current_start)s, 'value', 'previous')       AS period,
        SUM(total_cost) / SUM(liters)                                      AS price_per_liter
    FROM fct_fuel_purchases
    WHERE purchase_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
truck_maintenance AS (
    SELECT
        IFF(maintenance_date >= %(current_start)s, 'value', 'previous')    AS period,
        truck_key,
        SUM(total_cost)                                                    AS maintenance_cost
    FROM fct_maintenance
    WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period, truck_key
),
trips AS (
    SELECT
        IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')           AS period,
        truck_key,
        revenue_usd + fuel_surcharge_usd + accessorial_charges_usd         AS revenue,
        fuel_liters_used,
        actual_distance_km
    FROM fct_trips
    WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
      AND truck_key IS NOT NULL
),
trips_with_truck_km AS (
    SELECT *, SUM(actual_distance_km) OVER (PARTITION BY period, truck_key)   AS truck_distance_km
    FROM trips
)
SELECT
    t.period,
    AVG(t.revenue
        - t.fuel_liters_used * p.price_per_liter
        - COALESCE(m.maintenance_cost, 0) * t.actual_distance_km / t.truck_distance_km)   AS kpi_value
FROM trips_with_truck_km t
JOIN fuel_price p             ON p.period = t.period
LEFT JOIN truck_maintenance m  ON m.period = t.period AND m.truck_key = t.truck_key
GROUP BY t.period
