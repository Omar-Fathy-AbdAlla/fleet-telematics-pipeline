SELECT
    TRUCK_KEY,
    SNAPSHOT_DATE_KEY
FROM {{ ref('fct_truck_daily') }}
GROUP BY
    TRUCK_KEY,
    SNAPSHOT_DATE_KEY
HAVING COUNT(*) > 1