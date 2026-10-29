{{ config(materialized='table') }}

WITH location_candidates AS (

    -- Origin locations from routes
    SELECT
        ORIGIN_CITY AS CITY,
        ORIGIN_STATE AS STATE_CODE,
        NULL::NUMBER(12, 7) AS LATITUDE,
        NULL::NUMBER(12, 7) AS LONGITUDE
    FROM {{ ref('routes') }}

    UNION ALL

    -- Destination locations from routes
    SELECT
        DESTINATION_CITY AS CITY,
        DESTINATION_STATE AS STATE_CODE,
        NULL::NUMBER(12, 7) AS LATITUDE,
        NULL::NUMBER(12, 7) AS LONGITUDE
    FROM {{ ref('routes') }}

    UNION ALL

    -- Facility locations, including coordinates
    SELECT
        CITY,
        STATE AS STATE_CODE,
        LATITUDE,
        LONGITUDE
    FROM {{ ref('facilities') }}

),

deduplicated_locations AS (

    SELECT
        INITCAP(TRIM(CITY)) AS CITY,
        UPPER(TRIM(STATE_CODE)) AS STATE_CODE,
        AVG(LATITUDE) AS LATITUDE,
        AVG(LONGITUDE) AS LONGITUDE

    FROM location_candidates

    WHERE CITY IS NOT NULL
      AND TRIM(CITY) <> ''

    GROUP BY
        INITCAP(TRIM(CITY)),
        UPPER(TRIM(STATE_CODE))

),

final AS (

    SELECT
        ROW_NUMBER() OVER (
            ORDER BY CITY, STATE_CODE NULLS FIRST
        ) AS LOCATION_KEY,

        CITY,
        STATE_CODE,
        LATITUDE,
        LONGITUDE

    FROM deduplicated_locations

)

SELECT *
FROM final
