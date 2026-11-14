-- One row per real company: the master record's details, plus how many CRM records were merged into it.

with resolution as (
    select * from {{ ref('int_account_resolution') }}
),

accounts as (
    select * from {{ source('silver', 'salesforce_account') }}
)

select
    r.master_account_id   as account_id,
    a.account_name,
    r.company_key,
    a.domain,
    a.billing_city,
    a.billing_state,
    a.created_at,
    r.records_in_company  as source_record_count
from resolution r
join accounts a on a.account_id = r.account_id
where r.account_id = r.master_account_id      -- keep only each company's master record