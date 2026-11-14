-- Match each Stripe customer to a company by email domain.
-- Unmatched customers are kept, so their revenue never silently disappears from gold.

{{ config(materialized='view') }}

with customers as (
    select customer_id, customer_name, email_domain
    from {{ source('silver', 'stripe_customer') }}
),

companies as (
    select account_id, company_key
    from {{ ref('dim_account') }}
)

select
    c.customer_id,
    c.customer_name,
    c.email_domain,
    co.account_id,
    case
        when co.account_id is null then 'unmatched'
        else 'matched_on_domain'
    end as match_status
from customers c
left join companies co
    on c.email_domain = co.company_key