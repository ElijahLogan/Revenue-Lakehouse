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