{{ config(materialized='table') }}

WITH fuel_source AS (
    SELECT *
    FROM {{ ref('fuel_purchases') }}
    WHERE FUEL_PURCHASE_ID IS NOT NULL
),

final AS (
    SELECT
        f.FUEL_PURCHASE_ID,
        f.TRIP_ID,

        dd.DATE_KEY AS PURCHASE_DATE_KEY,
        dt.TRUCK_KEY,
        dr.DRIVER_KEY,

        f.PURCHASE_DATE,
        f.TRUCK_ID,
        f.DRIVER_ID,
        f.LOCATION_CITY,
        f.LOCATION_STATE,
        f.FUEL_CARD_NUMBER,

        f.LITERS,
        f.PRICE_PER_LITER,
        f.TOTAL_COST

    FROM fuel_source f

    LEFT JOIN {{ ref('dim_date') }} dd
        ON f.PURCHASE_DATE = dd.FULL_DATE

    LEFT JOIN {{ ref('dim_truck') }} dt
        ON f.TRUCK_ID = dt.TRUCK_ID

    LEFT JOIN {{ ref('dim_driver') }} dr
        ON f.DRIVER_ID = dr.DRIVER_ID
       AND f.PURCHASE_DATE >= dr.VALID_FROM
       AND f.PURCHASE_DATE <= dr.VALID_TO

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY f.FUEL_PURCHASE_ID
        ORDER BY
            f.PURCHASE_DATE DESC NULLS LAST,
            dr.VALID_FROM DESC NULLS LAST
    ) = 1
)

SELECT *
FROM final
