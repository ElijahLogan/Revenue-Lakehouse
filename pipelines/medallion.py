"""Bronze and silver layers as a Lakeflow Declarative Pipeline (formerly Delta Live Tables)."""

import dlt
from pyspark.sql import functions as F

LANDING = "/Volumes/revenue/raw/landing"

SOURCES = [
    ("salesforce", "account"),
    ("salesforce", "opportunity"),
    ("stripe", "customer"),
    ("stripe", "charge"),
]

# Salesforce timestamps look like 2026-10-31T03:36:31.000+0000
SF_TIMESTAMP = "yyyy-MM-dd'T'HH:mm:ss.SSSZ"


# ---------------------------------------------------------------------------
# Bronze: raw records as landed. No checkpoints or triggers to manage here;
# the pipeline handles them.
# ---------------------------------------------------------------------------

def bronze_table(source: str, entity: str) -> None:
    @dlt.table(
        name=f"revenue.bronze.{source}_{entity}",
        comment=f"Raw {source} {entity} records, exactly as landed.",
    )
    def _bronze():
        return (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.inferColumnTypes", "true")
            .load(f"{LANDING}/{source}/{entity}/")
            .withColumn("_file_path", F.col("_metadata.file_path"))
            .withColumn("_ingested_at", F.current_timestamp())
        )


for _source, _entity in SOURCES:
    bronze_table(_source, _entity)


# ---------------------------------------------------------------------------
# Silver: Salesforce accounts, typed, validated, one row per account.
# ---------------------------------------------------------------------------

@dlt.view(name="salesforce_account_updates")
@dlt.expect_or_drop("has_id", "account_id IS NOT NULL")
@dlt.expect("has_name", "account_name IS NOT NULL AND account_name <> ''")
def salesforce_account_updates():
    return spark.readStream.table("revenue.bronze.salesforce_account").select(
        F.col("payload.Id").alias("account_id"),
        F.trim("payload.Name").alias("account_name"),
        F.col("payload.Website").alias("website"),
        # https://www.Example.com/ -> example.com, so duplicates and Stripe emails can match later
        F.lower(
            F.regexp_replace(
                F.regexp_replace("payload.Website", r"^(https?://)?(www\.)?", ""), r"/.*$", ""
            )
        ).alias("domain"),
        F.col("payload.Phone").alias("phone"),
        F.col("payload.BillingCity").alias("billing_city"),
        F.col("payload.BillingState").alias("billing_state"),
        F.to_timestamp("payload.CreatedDate", SF_TIMESTAMP).alias("created_at"),
        F.to_timestamp("payload.SystemModstamp", SF_TIMESTAMP).alias("modified_at"),
        "_run_id",
        "_file_path",
    )


dlt.create_streaming_table(
    name="revenue.silver.salesforce_account",
    comment="Salesforce accounts: typed, validated, one row per account at its latest version.",
)

dlt.apply_changes(
    target="revenue.silver.salesforce_account",
    source="salesforce_account_updates",
    keys=["account_id"],
    # Latest change wins; file path breaks ties between identical copies from repeated pulls.
    sequence_by=F.struct("modified_at", "_file_path"),
    stored_as_scd_type=1,
)


# ---------------------------------------------------------------------------
# Silver: Salesforce opportunities
# ---------------------------------------------------------------------------

@dlt.view(name="salesforce_opportunity_updates")
@dlt.expect_or_drop("has_id", "opportunity_id IS NOT NULL")
@dlt.expect("non_negative_amount", "amount IS NULL OR amount >= 0")
def salesforce_opportunity_updates():
    return spark.readStream.table("revenue.bronze.salesforce_opportunity").select(
        F.col("payload.Id").alias("opportunity_id"),
        F.col("payload.AccountId").alias("account_id"),
        F.col("payload.Name").alias("opportunity_name"),
        F.col("payload.StageName").alias("stage"),
        F.col("payload.Amount").cast("decimal(18,2)").alias("amount"),
        F.to_date("payload.CloseDate").alias("close_date"),
        F.col("payload.IsWon").cast("boolean").alias("is_won"),
        F.to_timestamp("payload.SystemModstamp", SF_TIMESTAMP).alias("modified_at"),
        "_run_id",
        "_file_path",
    )


dlt.create_streaming_table(
    name="revenue.silver.salesforce_opportunity",
    comment="Salesforce opportunities: typed, one row per opportunity at its latest version.",
)

dlt.apply_changes(
    target="revenue.silver.salesforce_opportunity",
    source="salesforce_opportunity_updates",
    keys=["opportunity_id"],
    sequence_by=F.struct("modified_at", "_file_path"),
    stored_as_scd_type=1,
)


# ---------------------------------------------------------------------------
# Silver: Stripe customers (latest event per customer; deletes propagate)
# ---------------------------------------------------------------------------

@dlt.view(name="stripe_customer_updates")
@dlt.expect_or_drop("has_id", "customer_id IS NOT NULL")
def stripe_customer_updates():
    return spark.readStream.table("revenue.bronze.stripe_customer").select(
        F.col("payload.id").alias("customer_id"),
        F.col("payload.name").alias("customer_name"),
        F.lower(F.trim("payload.email")).alias("email"),
        F.lower(F.split("payload.email", "@").getItem(1)).alias("email_domain"),
        F.to_timestamp(F.from_unixtime("payload.created")).alias("created_at"),
        F.col("payload._event_created").cast("bigint").alias("event_created"),
        (F.col("payload._event_type") == "customer.deleted").alias("is_deleted"),
        "_run_id",
        "_file_path",
    )


dlt.create_streaming_table(
    name="revenue.silver.stripe_customer",
    comment="Stripe customers at their latest event. Deleted customers are removed.",
)

dlt.apply_changes(
    target="revenue.silver.stripe_customer",
    source="stripe_customer_updates",
    keys=["customer_id"],
    sequence_by=F.struct("event_created", "_file_path"),
    apply_as_deletes=F.expr("is_deleted"),
    stored_as_scd_type=1,
)


# ---------------------------------------------------------------------------
# Silver: Stripe charges, with a quarantine table for records that break the rules
# ---------------------------------------------------------------------------

CHARGE_RULES = {
    "has_id": "charge_id IS NOT NULL",
    "has_customer": "customer_id IS NOT NULL",
    "positive_amount": "amount > 0",
    "known_status": "status IN ('succeeded', 'pending', 'failed')",
}


@dlt.view(name="stripe_charge_staged")
def stripe_charge_staged():
    return spark.readStream.table("revenue.bronze.stripe_charge").select(
        F.col("payload.id").alias("charge_id"),
        F.col("payload.customer").alias("customer_id"),
        # Stripe sends integer cents. Convert to dollars once, here, at the boundary.
        (F.col("payload.amount").cast("decimal(18,2)") / 100).alias("amount"),
        (F.col("payload.amount_refunded").cast("decimal(18,2)") / 100).alias("amount_refunded"),
        F.upper("payload.currency").alias("currency"),
        F.col("payload.status").alias("status"),
        F.to_timestamp(F.from_unixtime("payload.created")).alias("charged_at"),
        F.col("payload._event_created").cast("bigint").alias("event_created"),
        F.col("payload._event_type").alias("event_type"),
        "_run_id",
        "_file_path",
    )


@dlt.table(
    name="revenue.silver.stripe_charge_quarantine",
    comment="Charge records that failed silver rules. Kept for inspection, not dropped.",
)
def stripe_charge_quarantine():
    failed_any = " OR ".join(f"NOT ({rule})" for rule in CHARGE_RULES.values())
    return dlt.read_stream("stripe_charge_staged").where(failed_any)


@dlt.view(name="stripe_charge_valid")
@dlt.expect_all_or_drop(CHARGE_RULES)
def stripe_charge_valid():
    return dlt.read_stream("stripe_charge_staged")


dlt.create_streaming_table(
    name="revenue.silver.stripe_charge",
    comment="Stripe charges in dollars at their latest event (refunds reflected).",
)

dlt.apply_changes(
    target="revenue.silver.stripe_charge",
    source="stripe_charge_valid",
    keys=["charge_id"],
    # Events in the same second tie on event_created. amount_refunded only ever increases,
    # so it breaks the tie in favor of the refunded snapshot.
    sequence_by=F.struct("event_created", "amount_refunded"),
    stored_as_scd_type=1,
)