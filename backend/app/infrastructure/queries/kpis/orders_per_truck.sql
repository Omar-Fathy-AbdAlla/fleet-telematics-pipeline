-- KPI 43 Orders per Truck (orders): COUNT(maintenance orders) / fleet trucks, per 30-day period (not annualised).
-- fleet trucks = distinct TRUCK_KEY in FCT_TRUCK_DAILY in the period.
-- Period date: MAINTENANCE_DATE for orders, snapshot date (DIM_DATE.FULL_DATE) for trucks.
WITH orders AS (
    SELECT
        IFF(maintenance_date >= %(current_start)s, 'value', 'previous')   AS period,
        COUNT(*)                                                          AS orders
    FROM fct_maintenance
    WHERE maintenance_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
),
fleet AS (
    SELECT
        IFF(d.full_date >= %(current_start)s, 'value', 'previous')        AS period,
        COUNT(DISTINCT f.truck_key)                                       AS trucks
    FROM fct_truck_daily f
    JOIN dim_date d ON d.date_key = f.snapshot_date_key
    WHERE d.full_date BETWEEN %(previous_start)s AND %(current_end)s
    GROUP BY period
)
SELECT
    f.period,
    COALESCE(o.orders, 0) / f.trucks                                      AS kpi_value
FROM fleet f
LEFT JOIN orders o ON o.period = f.period
