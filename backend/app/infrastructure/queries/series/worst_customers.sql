-- Chart worst_customers (Delivery): the 8 customers with the lowest KPI 1 On-Time Delivery Rate (pct), current period.
-- Customers with fewer than 10 deliveries are left out (assumption: too few to rank fairly).
-- DIM_CUSTOMER keeps history, so only the current row (is_current) is joined.
SELECT
    e.customer_id,
    c.customer_name,
    c.customer_type,
    COUNT(*)                                               AS deliveries,
    COUNT_IF(e.on_time_flag = 'TRUE') / COUNT(*) * 100     AS kpi_1
FROM fct_delivery_events e
JOIN dim_customer c ON c.customer_id = e.customer_id AND c.is_current
WHERE e.event_type = 'DELIVERY'
  AND e.actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY ALL
HAVING COUNT(*) >= 10
ORDER BY kpi_1, deliveries DESC
LIMIT 8
