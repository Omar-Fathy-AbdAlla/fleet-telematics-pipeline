{{ config(materialized='table') }}

WITH latest_trailer_snapshot AS (
    SELECT *
    FROM {{ ref('trailers') }}
    WHERE TRAILER_ID IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY TRAILER_ID
        ORDER BY SNAPSHOT_DATE DESC NULLS LAST
    ) = 1
),

final AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY TRAILER_ID
        )::INTEGER AS TRAILER_KEY,

        TRAILER_ID,
        TRAILER_NUMBER,
        TRAILER_TYPE,
        LENGTH_METERS,
        MODEL_YEAR,
        VIN,
        ACQUISITION_DATE

    FROM latest_trailer_snapshot
)

SELECT * FROM final