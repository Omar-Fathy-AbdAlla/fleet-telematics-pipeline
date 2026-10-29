-- KPI 8 Trip Duration Variance (pct): average over trips of (actual - planned) / planned x 100.
-- planned hours = scheduled DELIVERY datetime - scheduled PICKUP datetime of the trip (FCT_DELIVERY_EVENTS).
-- actual hours  = FCT_TRIPS.actual_duration_hours. Trips missing one of the two events give NULL and are skipped by AVG.
-- Period date: ARRIVAL_TS date (day the trip finished).
WITH trip_schedule AS (
    SELECT
        trip_id,
        DATEDIFF('minute',
                 MAX(IFF(event_type = 'PICKUP', scheduled_datetime, NULL)),
                 MAX(IFF(event_type = 'DELIVERY', scheduled_datetime, NULL))) / 60      AS planned_hours
    FROM fct_delivery_events
    GROUP BY trip_id
)
SELECT
    IFF(t.arrival_ts::DATE >= %(current_start)s, 'value', 'previous')                          AS period,
    AVG((t.actual_duration_hours - s.planned_hours) / NULLIF(s.planned_hours, 0) * 100)  AS kpi_value
FROM fct_trips t
JOIN trip_schedule s ON s.trip_id = t.trip_id
WHERE t.arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
