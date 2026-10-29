{{ config(materialized='table') }}

WITH events_source AS (

    SELECT *
    FROM {{ ref('delivery_events') }}
    WHERE EVENT_ID IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY EVENT_ID
        ORDER BY
            ACTUAL_DATETIME DESC NULLS LAST,
            SCHEDULED_DATETIME DESC NULLS LAST
    ) = 1

),

loads_deduplicated AS (

    SELECT
        LOAD_ID,
        LOAD_DATE,
        CUSTOMER_ID,
        ROUTE_ID
    FROM {{ ref('loads') }}
    WHERE LOAD_ID IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY LOAD_ID
        ORDER BY LOAD_DATE DESC NULLS LAST
    ) = 1

),

final AS (

    SELECT
        e.EVENT_ID,
        e.LOAD_ID,
        e.TRIP_ID,

        d.DATE_KEY AS LOAD_DATE_KEY,
        l.CUSTOMER_ID,
        l.ROUTE_ID,

        e.FACILITY_ID,
        e.EVENT_TYPE,
        e.ON_TIME_FLAG,

        e.LOCATION_CITY,
        e.LOCATION_STATE,

        e.SCHEDULED_DATETIME,
        e.ACTUAL_DATETIME,

        TO_DATE(e.SCHEDULED_DATETIME) AS SCHEDULED_DATE,
        TO_DATE(e.ACTUAL_DATETIME) AS ACTUAL_DATE,

        e.DETENTION_MINUTES,

        CASE
            WHEN e.ACTUAL_DATETIME IS NOT NULL
             AND e.SCHEDULED_DATETIME IS NOT NULL
            THEN DATEDIFF(
                'minute',
                e.SCHEDULED_DATETIME,
                e.ACTUAL_DATETIME
            )
            ELSE NULL
        END AS DELAY_MINUTES,

        CASE
            WHEN e.ACTUAL_DATETIME IS NULL
              OR e.SCHEDULED_DATETIME IS NULL
                THEN 'Unknown'
            WHEN e.ACTUAL_DATETIME > e.SCHEDULED_DATETIME
                THEN 'Late'
            ELSE 'On Time'
        END AS CALCULATED_DELIVERY_STATUS

    FROM events_source e

    LEFT JOIN loads_deduplicated l
        ON e.LOAD_ID = l.LOAD_ID

    LEFT JOIN {{ ref('dim_date') }} d
        ON l.LOAD_DATE = d.FULL_DATE

)

SELECT *
FROM final