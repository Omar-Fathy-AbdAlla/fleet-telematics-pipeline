-- Chart incidents_by_type (Safety): incident count and total claim_amount (USD) per incident_type, current period.
SELECT
    incident_type,
    COUNT(*)            AS incidents,
    SUM(claim_amount)   AS claim_amount
FROM fct_safety_incidents
WHERE incident_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY incident_type
ORDER BY claim_amount DESC
