{{ config(materialized='table') }}

WITH trips_source AS (
    SELECT *
    FROM {{ ref('trips') }}
    WHERE TRIP_ID IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY TRIP_ID
        ORDER BY ARRIVAL_TS DESC NULLS LAST,
                 DISPATCH_TS DESC NULLS LAST
    ) = 1
),

loads_source AS (
    SELECT *
    FROM {{ ref('loads') }}
    WHERE LOAD_ID IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY LOAD_ID
        ORDER BY LOAD_DATE DESC NULLS LAST
    ) = 1
),

trip_load AS (
    SELECT
        t.TRIP_ID,
        t.LOAD_ID,
        t.TRUCK_ID,
        t.TRAILER_ID,
        t.DRIVER_ID,
        t.DISPATCH_TS,
        t.ARRIVAL_TS,

        COALESCE(
            t.DISPATCH_DATE,
            TO_DATE(t.DISPATCH_TS),
            l.LOAD_DATE
        ) AS TRIP_DATE,

        t.TRIP_STATUS,
        t.AVERAGE_L_PER_100KM,
        t.IDLE_TIME_HOURS,
        t.FUEL_LITERS_USED,
        t.ACTUAL_DISTANCE_KM,
        t.ACTUAL_DURATION_HOURS,

        l.CUSTOMER_ID,
        l.ROUTE_ID,
        l.LOAD_TYPE,
        l.BOOKING_TYPE,
        l.PIECES,
        l.WEIGHT_KG,
        l.FUEL_SURCHARGE,
        l.REVENUE,
        l.ACCESSORIAL_CHARGES,
        l.LOAD_STATUS,
        l.LOAD_DATE

    FROM trips_source t
    LEFT JOIN loads_source l
        ON t.LOAD_ID = l.LOAD_ID
),

final AS (
    SELECT
        tl.TRIP_ID,
        tl.LOAD_ID,

        dd.DATE_KEY AS DISPATCH_DATE_KEY,
        dc.CUSTOMER_KEY,
        droute.ROUTE_KEY,
        dt.TRUCK_KEY,
        dtr.TRAILER_KEY,
        dr.DRIVER_KEY,

        -- Keep source identifiers for traceability.
        tl.CUSTOMER_ID,
        tl.ROUTE_ID,
        tl.TRUCK_ID,
        tl.TRAILER_ID,
        tl.DRIVER_ID,

        tl.TRIP_STATUS,
        tl.LOAD_STATUS,
        tl.LOAD_TYPE,
        tl.BOOKING_TYPE,
        tl.PIECES,
        tl.WEIGHT_KG,

        tl.DISPATCH_TS,
        tl.ARRIVAL_TS,
        tl.ACTUAL_DURATION_HOURS,
        tl.ACTUAL_DISTANCE_KM,
        tl.FUEL_LITERS_USED,
        tl.AVERAGE_L_PER_100KM,
        tl.IDLE_TIME_HOURS,

        tl.REVENUE AS REVENUE_USD,
        tl.FUEL_SURCHARGE AS FUEL_SURCHARGE_USD,
        tl.ACCESSORIAL_CHARGES AS ACCESSORIAL_CHARGES_USD,

        tl.LOAD_DATE,
        tl.TRIP_DATE

    FROM trip_load tl

    LEFT JOIN {{ ref('dim_date') }} dd
        ON tl.TRIP_DATE = dd.FULL_DATE

    LEFT JOIN {{ ref('dim_customer') }} dc
        ON tl.CUSTOMER_ID = dc.CUSTOMER_ID

    LEFT JOIN {{ ref('dim_route') }} droute
        ON tl.ROUTE_ID = droute.ROUTE_ID

    LEFT JOIN {{ ref('dim_truck') }} dt
        ON tl.TRUCK_ID = dt.TRUCK_ID

    LEFT JOIN {{ ref('dim_trailer') }} dtr
        ON tl.TRAILER_ID = dtr.TRAILER_ID

    LEFT JOIN {{ ref('dim_driver') }} dr
        ON tl.DRIVER_ID = dr.DRIVER_ID
        AND tl.TRIP_DATE >= dr.VALID_FROM
        AND tl.TRIP_DATE <= dr.VALID_TO

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY tl.TRIP_ID
        ORDER BY dr.VALID_FROM DESC NULLS LAST
    ) = 1
)

SELECT *
FROM final
