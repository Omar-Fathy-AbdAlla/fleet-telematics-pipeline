{{ config(materialized='table') }}

WITH latest_truck_snapshot AS (
    SELECT *
    FROM {{ ref('trucks') }}
    WHERE TRUCK_ID IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY TRUCK_ID
        ORDER BY SNAPSHOT_DATE DESC NULLS LAST
    ) = 1
),

final AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY T.TRUCK_ID
        )::INTEGER AS TRUCK_KEY,

        T.TRUCK_ID,
        T.UNIT_NUMBER,
        T.MAKE,
        T.MODEL_YEAR,
        T.VIN,
        T.FUEL_TYPE,
        T.TANK_CAPACITY_LITERS,
        T.ACQUISITION_DATE,
        T.ACQUISITION_MILEAGE_KM,
        L.LOCATION_KEY AS HOME_TERMINAL_LOCATION_KEY

    FROM latest_truck_snapshot T

    LEFT JOIN {{ ref('dim_location') }} L
        ON UPPER(TRIM(T.HOME_TERMINAL)) = UPPER(TRIM(L.CITY))
)

SELECT * FROM final