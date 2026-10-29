-- KPI 6 Destination Queue Time (min): average of delivery actual_datetime - trip arrival_ts.
-- Join: FCT_DELIVERY_EVENTS -> FCT_TRIPS on TRIP_ID (events of trips not completed yet have no match). Period date: ACTUAL_DATE.
SELECT
    IFF(e.actual_date >= %(current_start)s, 'value', 'previous')     AS period,
    AVG(DATEDIFF('minute', t.arrival_ts, e.actual_datetime))         AS kpi_value
FROM fct_delivery_events e
JOIN fct_trips t ON t.trip_id = e.trip_id
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
