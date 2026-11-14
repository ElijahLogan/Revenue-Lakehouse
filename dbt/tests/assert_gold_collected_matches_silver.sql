-- Fails (returns a row) if gold's collected total differs from silver's by more than a cent.

with silver_total as (
    select coalesce(sum(amount - amount_refunded), 0) as total
    from {{ source('silver', 'stripe_charge') }}
    where status = 'succeeded'
),

gold_total as (
    select coalesce(sum(collected_usd), 0) as total
    from {{ ref('fct_revenue_by_account') }}
)

select s.total as silver_total, g.total as gold_total
from silver_total s
cross join gold_total g
where abs(s.total - g.total) > 0.01