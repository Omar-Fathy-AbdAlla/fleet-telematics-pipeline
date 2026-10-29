{{ config(materialized='table') }}

WITH cleaned_customers AS (
    SELECT DISTINCT
        CUSTOMER_ID,
        CUSTOMER_NAME,
        CUSTOMER_TYPE,
        ACCOUNT_STATUS,
        CREDIT_TERMS_DAYS,
        CONTRACT_START_DATE,
        PRIMARY_FREIGHT_TYPE,
        ANNUAL_REVENUE_POTENTIAL
    FROM {{ ref('customers') }}
    WHERE CUSTOMER_ID IS NOT NULL
),

one_row_per_customer AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY CUSTOMER_ID
        )::INTEGER AS CUSTOMER_KEY,

        CUSTOMER_ID,
        CUSTOMER_NAME,
        CUSTOMER_TYPE,
        ACCOUNT_STATUS,
        CREDIT_TERMS_DAYS,
        PRIMARY_FREIGHT_TYPE,
        CONTRACT_START_DATE,

        ANNUAL_REVENUE_POTENTIAL
            AS ANNUAL_REVENUE_POTENTIAL_USD,

        COALESCE(
            CONTRACT_START_DATE,
            CURRENT_DATE()
        ) AS VALID_FROM,

        TO_DATE('9999-12-31') AS VALID_TO,
        TRUE AS IS_CURRENT

    FROM cleaned_customers

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY CUSTOMER_ID
        ORDER BY CONTRACT_START_DATE DESC NULLS LAST
    ) = 1
)

SELECT * FROM one_row_per_customer