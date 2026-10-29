-- KPI 26 Revenue per km (USD/km): SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / SUM(actual_distance_km).
-- Period date: ARRIVAL_TS date (day the trip finished).
SELECT
    IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')                                     AS period,
    SUM(revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / SUM(actual_distance_km)    AS kpi_value
FROM fct_trips
WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
