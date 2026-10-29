{{ config(materialized='table') }}

WITH truck_snapshots AS (

    SELECT
        TRUCK_ID,
        SNAPSHOT_DATE,
        STATUS AS TRUCK_STATUS
    FROM {{ ref('trucks') }}
    WHERE TRUCK_ID IS NOT NULL
      AND SNAPSHOT_DATE IS NOT NULL

),

daily_trips AS (

    SELECT
        TRUCK_KEY,
        TO_DATE(ARRIVAL_TS) AS SNAPSHOT_DATE,
        COUNT(*) AS TRIPS_COMPLETED
    FROM {{ ref('fct_trips') }}
    WHERE TRIP_STATUS = 'Completed'
      AND ARRIVAL_TS IS NOT NULL
      AND TRUCK_KEY IS NOT NULL
    GROUP BY
        TRUCK_KEY,
        TO_DATE(ARRIVAL_TS)

),

daily_maintenance AS (

    SELECT
        TRUCK_KEY,
        MAINTENANCE_DATE_KEY AS SNAPSHOT_DATE_KEY,
        1 AS HAS_MAINTENANCE_RECORD
    FROM {{ ref('fct_maintenance') }}
    WHERE TRUCK_KEY IS NOT NULL
      AND MAINTENANCE_DATE_KEY IS NOT NULL
    GROUP BY
        TRUCK_KEY,
        MAINTENANCE_DATE_KEY

)

SELECT
    DT.TRUCK_KEY,
    DD.DATE_KEY AS SNAPSHOT_DATE_KEY,
    TS.TRUCK_STATUS,

    COALESCE(DM.HAS_MAINTENANCE_RECORD, 0) = 1
        AS IS_IN_MAINTENANCE,

    COALESCE(DT2.TRIPS_COMPLETED, 0)
        AS TRIPS_COMPLETED

FROM truck_snapshots TS

INNER JOIN {{ ref('dim_truck') }} DT
    ON TS.TRUCK_ID = DT.TRUCK_ID

INNER JOIN {{ ref('dim_date') }} DD
    ON TS.SNAPSHOT_DATE = DD.FULL_DATE

LEFT JOIN daily_trips DT2
    ON DT.TRUCK_KEY = DT2.TRUCK_KEY
   AND TS.SNAPSHOT_DATE = DT2.SNAPSHOT_DATE

LEFT JOIN daily_maintenance DM
    ON DT.TRUCK_KEY = DM.TRUCK_KEY
   AND DD.DATE_KEY = DM.SNAPSHOT_DATE_KEY