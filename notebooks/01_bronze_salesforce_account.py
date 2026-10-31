from pyspark.sql import functions as F

LANDING = "/Volumes/revenue/raw/landing"
SOURCE = f"{LANDING}/salesforce/account/"
CHECKPOINT = f"{LANDING}/_checkpoints/bronze_salesforce_account"
TARGET = "revenue.bronze.salesforce_account"

query = (
    spark.readStream.format("cloudFiles")                    # Auto Loader
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", f"{CHECKPOINT}/schema")
    .option("cloudFiles.inferColumnTypes", "true")
    .load(SOURCE)
    .withColumn("_file_path", F.col("_metadata.file_path"))  # which file each row came from
    .withColumn("_ingested_at", F.current_timestamp())       # when bronze loaded it
    .writeStream
    .option("checkpointLocation", CHECKPOINT)
    .trigger(availableNow=True)                              # process new files, then stop
    .toTable(TARGET)
)
query.awaitTermination()