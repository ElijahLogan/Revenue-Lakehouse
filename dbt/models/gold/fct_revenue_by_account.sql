-- Booked (won opportunities in Salesforce) vs. collected (net succeeded payments in Stripe),
-- per company. Payments from customers not in the CRM are kept under an UNMATCHED: key.

with booked as (

    select
        r.master_account_id as account_id,
        sum(o.amount)       as booked_usd
    from {{ source('silver', 'salesforce_opportunity') }} o
    join {{ ref('int_account_resolution') }} r
        on r.account_id = o.account_id          -- duplicate records roll up to their master
    where o.is_won
    group by r.master_account_id

),

collected as (

    select
        coalesce(m.account_id, 'UNMATCHED:' || ch.customer_id) as account_id,
        max(m.customer_name)                     as stripe_customer_name,
        sum(ch.amount - ch.amount_refunded)      as collected_usd
    from {{ source('silver', 'stripe_charge') }} ch
    left join {{ ref('int_customer_account_match') }} m
        on m.customer_id = ch.customer_id
    where ch.status = 'succeeded'
    group by 1

),

joined as (

    select
        coalesce(b.account_id, c.account_id)             as account_key,
        coalesce(d.account_name, c.stripe_customer_name) as company_name,
        coalesce(b.booked_usd, 0)                        as booked_usd,
        coalesce(c.collected_usd, 0)                     as collected_usd
    from booked b
    full outer join collected c on c.account_id = b.account_id
    left join {{ ref('dim_account') }} d on d.account_id = coalesce(b.account_id, c.account_id)

)

select
    account_key,
    company_name,
    booked_usd,
    collected_usd,
    collected_usd - booked_usd as variance_usd,
    case
        when account_key like 'UNMATCHED:%' then 'paid_not_in_crm'
        when collected_usd = 0              then 'booked_not_paid'
        when booked_usd = 0                 then 'paid_not_booked'
        when collected_usd = booked_usd     then 'reconciled'
        when collected_usd < booked_usd     then 'underpaid'
        else 'overpaid'
    end as reconciliation_status
from joined