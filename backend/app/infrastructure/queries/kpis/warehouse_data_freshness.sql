-- KPI 65 Warehouse Data Freshness (min): now - the newest Airbyte load (_AIRBYTE_EXTRACTED_AT) over the 13 RAW_DATA tables.
-- A point in time, not a period: only 'value' (previous stays null). The period parameters are not used.
SELECT
    'value'                                                                   AS period,
    ROUND(DATEDIFF('second', MAX(loaded_at), CURRENT_TIMESTAMP()) / 60, 1)   AS kpi_value
FROM (
    SELECT MAX(_airbyte_extracted_at) AS loaded_at FROM raw_data.customers
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.delivery_events
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.diesel_prices
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.drivers
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.facilities
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.fuel_purchases
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.loads
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.maintenance_records
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.routes
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.safety_incidents
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.trailers
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.trips
    UNION ALL SELECT MAX(_airbyte_extracted_at) FROM raw_data.trucks
)
