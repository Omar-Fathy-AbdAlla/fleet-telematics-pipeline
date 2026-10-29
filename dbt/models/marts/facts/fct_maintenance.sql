
{{ config(materialized='table') }}

WITH maintenance_source AS (

    SELECT *
    FROM {{ ref('maintenance_records') }}
    WHERE MAINTENANCE_ID IS NOT NULL

),

deduplicated AS (

    SELECT *
    FROM maintenance_source

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY MAINTENANCE_ID
        ORDER BY MAINTENANCE_DATE DESC NULLS LAST
    ) = 1

),

final AS (

    SELECT
        m.MAINTENANCE_ID,

        -- Dimension keys
        dd.DATE_KEY AS MAINTENANCE_DATE_KEY,
        dt.TRUCK_KEY,
        dl.LOCATION_KEY,
        df.FACILITY_KEY,

        -- Maintenance details
        m.MAINTENANCE_DATE,
        m.TRUCK_ID,
        m.FACILITY_LOCATION,

        m.MAINTENANCE_TYPE,
        m.SERVICE_DESCRIPTION,

        -- Financial measures
        m.LABOR_COST,
        m.PARTS_COST,
        m.TOTAL_COST,

        -- Operational measures
        m.LABOR_HOURS,
        m.DOWNTIME_HOURS,
        m.ODOMETER_READING_KM

    FROM deduplicated m

    LEFT JOIN {{ ref('dim_date') }} dd
        ON m.MAINTENANCE_DATE = dd.FULL_DATE

    LEFT JOIN {{ ref('dim_truck') }} dt
        ON m.TRUCK_ID = dt.TRUCK_ID

    LEFT JOIN {{ ref('dim_location') }} dl
        ON UPPER(TRIM(m.FACILITY_LOCATION)) =
           UPPER(TRIM(dl.CITY))

    LEFT JOIN {{ ref('dim_facility') }} df
        ON UPPER(TRIM(m.FACILITY_LOCATION)) =
           UPPER(TRIM(df.FACILITY_NAME))

)

SELECT *
FROM final
