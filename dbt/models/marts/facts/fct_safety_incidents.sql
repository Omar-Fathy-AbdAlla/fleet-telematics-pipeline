{{ config(materialized='table') }}

WITH incident_source AS (

    SELECT *
    FROM {{ ref('safety_incidents') }}
    WHERE INCIDENT_ID IS NOT NULL

),

deduplicated AS (

    SELECT *
    FROM incident_source

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY INCIDENT_ID
        ORDER BY INCIDENT_DATE DESC NULLS LAST
    ) = 1

),

final AS (

    SELECT
        i.INCIDENT_ID,

        dd.DATE_KEY AS INCIDENT_DATE_KEY,
        dt.TRUCK_KEY,
        dr.DRIVER_KEY,

        i.TRIP_ID,
        i.INCIDENT_DATE,
        i.TRUCK_ID,
        i.DRIVER_ID,

        i.INCIDENT_TYPE,
        i.DESCRIPTION,
        i.INJURY_FLAG,
        i.AT_FAULT_FLAG,
        i.PREVENTABLE_FLAG,

        i.CLAIM_AMOUNT,
        i.CARGO_DAMAGE_COST,
        i.VEHICLE_DAMAGE_COST,

        i.LOCATION_CITY,
        i.LOCATION_STATE

    FROM deduplicated i

    LEFT JOIN {{ ref('dim_date') }} dd
        ON i.INCIDENT_DATE = dd.FULL_DATE

    LEFT JOIN {{ ref('dim_truck') }} dt
        ON i.TRUCK_ID = dt.TRUCK_ID

    LEFT JOIN {{ ref('dim_driver') }} dr
        ON i.DRIVER_ID = dr.DRIVER_ID
       AND i.INCIDENT_DATE >= dr.VALID_FROM
       AND i.INCIDENT_DATE <= dr.VALID_TO

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY i.INCIDENT_ID
        ORDER BY dr.VALID_FROM DESC NULLS LAST
    ) = 1

)

SELECT *
FROM final
