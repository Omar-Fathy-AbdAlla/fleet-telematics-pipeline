-- Chart cost_by_model_year (Maintenance): KPI 44 Maintenance Cost per km (USD/km) per truck model_year, current period.
-- Per model year: SUM(maintenance total_cost) / SUM(trips' actual_distance_km) of its trucks. Same rule as kpis/maintenance_cost_per_km.sql.
WITH maintenance AS (
    SELECT tr.model_year, SUM(m.total_cost)         AS maintenance_cost
    FROM fct_maintenance m
    JOIN dim_truck tr ON tr.truck_key = m.truck_key
    WHERE m.maintenance_date BETWEEN %(current_start)s AND %(current_end)s
    GROUP BY tr.model_year
),
trip_km AS (
    SELECT tr.model_year, SUM(t.actual_distance_km) AS distance_km
    FROM fct_trips t
    JOIN dim_truck tr ON tr.truck_key = t.truck_key
    WHERE t.arrival_ts::DATE BETWEEN %(current_start)s AND %(current_end)s
    GROUP BY tr.model_year
)
SELECT
    k.model_year,
    COALESCE(m.maintenance_cost, 0) / k.distance_km   AS kpi_44
FROM trip_km k
LEFT JOIN maintenance m ON m.model_year = k.model_year
ORDER BY k.model_year
