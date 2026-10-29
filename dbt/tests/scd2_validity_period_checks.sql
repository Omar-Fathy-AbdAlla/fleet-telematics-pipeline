WITH ordered_versions AS (

    SELECT
        DRIVER_ID AS ENTITY_ID,
        VALID_FROM,
        VALID_TO,
        IS_CURRENT,

        LEAD(VALID_FROM) OVER (
            PARTITION BY DRIVER_ID
            ORDER BY VALID_FROM
        ) AS NEXT_VALID_FROM

    FROM {{ ref('dim_driver') }}

)

SELECT *
FROM ordered_versions
WHERE VALID_TO < VALID_FROM

   OR (IS_CURRENT = TRUE AND VALID_TO <> TO_DATE('9999-12-31'))

   OR (IS_CURRENT = FALSE AND VALID_TO IS NULL)

   OR (
       NEXT_VALID_FROM IS NOT NULL
       AND (
           VALID_TO IS NULL
           OR VALID_TO >= NEXT_VALID_FROM
       )
   )
