WITH source_data AS (
    SELECT * FROM {{ source('raw_data', 'diesel_prices') }}
),
cleaned AS (
    SELECT
        INITCAP(NULLIF(TRIM(SOURCE), '')) AS SOURCE,
        INITCAP(NULLIF(TRIM(FUEL_TYPE), '')) AS FUEL_TYPE,
        TRY_TO_DATE(NULLIF(TRIM(EFFECTIVE_DATE), '')) AS EFFECTIVE_DATE,
        ROUND(
            TRY_TO_NUMBER(NULLIF(TRIM(PRICE_PER_GALLON), ''), 18, 4) / 3.78541, 
            4
        ) AS PRICE_PER_LITER
    FROM source_data
)
SELECT * FROM cleaned