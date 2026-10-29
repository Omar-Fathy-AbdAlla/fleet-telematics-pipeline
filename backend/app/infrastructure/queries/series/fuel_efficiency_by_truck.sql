-- Chart fuel_efficiency_by_truck (Fuel): the 10 least fuel-efficient trucks by KPI 21 Fuel Efficiency (L/100km, highest first),
-- current period. Trips without TRUCK_KEY are left out.
SELECT
    tr.truck_id,
    tr.make,
    AVG(t.average_l_per_100km)   AS kpi_21
FROM fct_trips t
JOIN dim_truck tr ON tr.truck_key = t.truck_key
WHERE t.arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY kpi_21 DESC
LIMIT 10
