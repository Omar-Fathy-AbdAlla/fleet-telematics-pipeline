-- KPI 46 Truck Availability (pct): truck-days not in maintenance / all truck-days x 100.
-- In maintenance = FCT_TRUCK_DAILY.is_in_maintenance (chosen over truck_status: the two columns disagree).
-- Period date: snapshot date (DIM_DATE.FULL_DATE).
SELECT
    IFF(d.full_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(NOT f.is_in_maintenance) / COUNT(*) * 100           AS kpi_value
FROM fct_truck_daily f
JOIN dim_date d ON d.date_key = f.snapshot_date_key
WHERE d.full_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
