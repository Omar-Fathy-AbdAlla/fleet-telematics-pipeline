-- Chart lane_otd (Delivery lane map + heatmap): KPI 1 On-Time Delivery Rate (pct) and delivery count per route,
-- current period. Coordinates come from DIM_LOCATION (origin and destination city) to draw the lane on the map.
SELECT
    r.route_id,
    o.city                                                 AS origin_city,
    o.state_code                                           AS origin_state,
    d.city                                                 AS destination_city,
    d.state_code                                           AS destination_state,
    r.typical_distance_km,
    o.latitude                                             AS origin_latitude,
    o.longitude                                            AS origin_longitude,
    d.latitude                                             AS destination_latitude,
    d.longitude                                            AS destination_longitude,
    COUNT(*)                                               AS deliveries,
    COUNT_IF(e.on_time_flag = 'TRUE') / COUNT(*) * 100     AS kpi_1
FROM fct_delivery_events e
JOIN dim_route r    ON r.route_id = e.route_id
JOIN dim_location o ON o.location_key = r.origin_location_key
JOIN dim_location d ON d.location_key = r.destination_location_key
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
ORDER BY r.route_id
