-- KPI 38 Claim Cost (USD): sum of safety incident claim_amount. Period date: INCIDENT_DATE.
SELECT
    IFF(incident_date >= %(current_start)s, 'value', 'previous')   AS period,
    SUM(claim_amount)                                              AS kpi_value
FROM fct_safety_incidents
WHERE incident_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
