-- Chart facility_queue (Delivery): the 10 facilities with the longest KPI 6 Destination Queue Time (min), current period.
-- Same rule as kpis/destination_queue_time.sql.
SELECT
    f.facility_id,
    f.facility_name,
    l.city,
    AVG(DATEDIFF('minute', t.arrival_ts, e.actual_datetime))   AS kpi_6
FROM fct_delivery_events e
JOIN fct_trips t    ON t.trip_id = e.trip_id
JOIN dim_facility f ON f.facility_id = e.facility_id
JOIN dim_location l ON l.location_key = f.location_key
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY kpi_6 DESC
LIMIT 10
