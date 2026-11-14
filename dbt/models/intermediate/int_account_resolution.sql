-- Map every Salesforce account record to one master account per real company.
-- Records sharing a normalized domain are the same company; the oldest one is the master.

-- {{ config(materialized='view') }}

with accounts as (

    select
        account_id,
        account_name,
        domain,
        created_at,
        coalesce(domain, account_id) as company_key   -- no website: the account stands alone
    from {{ source('silver', 'salesforce_account') }}

)

select
    account_id,
    account_name,
    company_key,
    first_value(account_id) over (
        partition by company_key
        order by created_at, account_id     -- oldest wins; account_id breaks ties
    ) as master_account_id,
    count(*) over (partition by company_key) as records_in_company
from accounts