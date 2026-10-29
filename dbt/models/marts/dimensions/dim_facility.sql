{{ config(materialized='table') }}

WITH source_facilities AS (

    SELECT
        FACILITY_ID,
        FACILITY_NAME,
        FACILITY_TYPE,
        CITY,
        STATE,
        LATITUDE,
        LONGITUDE,
        DOCK_DOORS,
        OPERATING_HOURS

    FROM {{ ref('facilities') }}

    WHERE FACILITY_ID IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY FACILITY_ID
        ORDER BY FACILITY_ID
    ) = 1

),

final AS (

    SELECT
        ROW_NUMBER() OVER (
            ORDER BY F.FACILITY_ID
        ) AS FACILITY_KEY,

        F.FACILITY_ID,
        F.FACILITY_NAME,
        F.FACILITY_TYPE,
        L.LOCATION_KEY,
        F.LATITUDE,
        F.LONGITUDE,
        F.DOCK_DOORS,
        F.OPERATING_HOURS

    FROM source_facilities F

    LEFT JOIN {{ ref('dim_location') }} L
        ON UPPER(TRIM(F.CITY)) = UPPER(TRIM(L.CITY))
       AND UPPER(TRIM(F.STATE)) = UPPER(TRIM(L.STATE_CODE))

)

SELECT *
FROM final
