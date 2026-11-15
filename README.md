# Revenue Lakehouse
 
[![CI](https://github.com/ElijahLogan/Revenue-Lakehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/ElijahLogan/Revenue-Lakehouse/actions/workflows/ci.yml)
 
A revenue data lakehouse on **Databricks** that brings together **Salesforce** (what sales says was won) and **Stripe** (what customers actually paid). The gold layer reconciles the two: bookings vs. collections, deals won but never paid, customers that only exist in billing, and duplicate accounts that would otherwise hide where the gaps are.
 
It runs end to end on a daily schedule: extract → raw → bronze → silver → gold, with tests at every layer.
 
## The result
 
`revenue.gold.fct_revenue_by_account`, built from the seed data:
 
| Company | Booked | Collected | Variance | Status |
|---|---:|---:|---:|---|
| Cedar & Pine Studio | 4,000 | 4,000 | 0 | reconciled |
| Juniper Foods | 5,000 | 5,000 | 0 | reconciled |
| Northwind Health | 6,000 | 6,000 | 0 | reconciled |
| Harbor Analytics | 2,500 | 2,000 | −500 | underpaid |
| Brightline Logistics | 3,000 | 2,000 | −1,000 | underpaid |
| Atlas Robotics | 2,400 | 1,000 | −1,400 | underpaid |
| Keystone Legal | 1,200 | 0 | −1,200 | booked_not_paid |
| Lumen Coffee | 0 | 2,000 | +2,000 | paid_not_in_crm |
| Quarry Fitness | 0 | 2,000 | +2,000 | paid_not_in_crm |
 
Harbor Analytics exists as **three** Salesforce records. Its $500 gap comes from a deal on one of the duplicates. Entity resolution rolls that deal up to Harbor's line, where it belongs, instead of leaving it under an unrecognizable duplicate account.
 
## Architecture
 
```
Salesforce (Accounts, Opportunities)      Stripe (Events API: customers, charges)
              │                                          │
              └──────────── Python extractors ───────────┘
                    incremental, watermark-based (GitHub Actions, daily)
                                     │
                                     ▼
          raw     /Volumes/revenue/raw/landing   NDJSON, one file per run, never overwritten
                                     │  Auto Loader
                                     ▼
          bronze  revenue.bronze.*                raw records as landed, plus file lineage
                                     │  Lakeflow Declarative Pipeline
                                     ▼
          silver  revenue.silver.*                typed, validated, one row per record
                                     │  dbt
                                     ▼
    intermediate  revenue.intermediate.*          entity resolution, Salesforce↔Stripe matching
                                     │  dbt
                                     ▼
          gold    revenue.gold.*                  dim_account, fct_revenue_by_account (analysts read only this)
```
 
Everything lives in one Unity Catalog catalog, `revenue`, with one schema per layer.
 
## Repository layout
 
| Path | What it does |
|---|---|
| `main.tf`, `variables.tf`, `outputs.tf` | Terraform: catalog schemas, landing volume, and gold-only analyst grants |
| `extract/salesforce_extract.py` | Incremental pull of Salesforce Accounts and Opportunities, filtered on `SystemModstamp` |
| `extract/stripe_extract.py` | Incremental pull of Stripe via the Events API, grouped into `customer` and `charge` files |
| `extract/watermarks.py` | Stores each source's last-seen position in `_state/watermarks.json` on the volume |
| `extract/records.py` | Wraps each record in a lineage envelope and builds date-partitioned landing paths |
| `extract/volume.py` | Small client for the Databricks Files API (read and write files in a UC volume) |
| `extract/seed*.py`, `extract/stripe_seed.py` | Seed a Salesforce dev org and Stripe test mode with deliberately messy data |
| `pipelines/medallion.py` | Lakeflow Declarative Pipeline (formerly DLT): bronze for all sources, silver for all four entities |
| `dbt/` | Gold layer: source tests, entity resolution, matching, the revenue mart, and a reconciliation test |
| `orchestrate/run_pipeline.py` | Starts a pipeline update through the Databricks API and waits for it to finish |
| `.github/workflows/ci.yml` | Unit tests and `dbt parse` on every pull request |
| `.github/workflows/refresh.yml` | Daily refresh: extract, run the pipeline, `dbt build` |
| `notebooks/01_bronze_salesforce_account.py` | Earlier hand-written Auto Loader notebook for one bronze table, kept to show the progression |
| `tests/` | Unit tests for records, watermarks, and Stripe event grouping |
| `DEVLOG.md` | Running log of problems hit and how they were solved |
 
## Design decisions
 
### Extraction
 
**Raw data is append-only.** Each run writes a new file at `<source>/<entity>/run_date=YYYY-MM-DD/<run_id>.json`. Nothing in the landing volume is overwritten, so every downstream layer can be rebuilt from raw.
 
**Every record carries lineage.** Records are landed as NDJSON wrapped in an envelope:
 
```json
{"_source": "salesforce", "_entity": "account", "_run_id": "2026-10-31T03-36-31Z",
 "_extracted_at": "2026-10-31T03:36:31Z", "payload": { ... }}
```
 
Bronze adds `_file_path` and `_ingested_at`, so every row can be traced to the file and run that produced it.
 
**Extracts are incremental.**
- *Salesforce* filters on `SystemModstamp > <watermark>`. The first run uses `1970-01-01` and pulls everything.
- *Stripe* reads the **Events API** instead of list endpoints. List endpoints filter on creation date, so they miss later changes like a refund on an old charge. Events capture every change.
- Watermarks are **saved only after every file has landed**, so a failed run is re-pulled instead of skipped. Delivery is at-least-once, and silver removes the duplicates.
- The extractors run **sequentially**, and overlapping runs are blocked, because both read and write the same watermark file.
### Silver
 
**One row per record, at its latest version.** `apply_changes` (SCD type 1) upserts by each entity's key, so repeated pulls and backfills never create duplicates.
 
**Problems are fixed once, at the boundary.**
- Stripe's integer cents are converted to dollars.
- Refunds overwrite the original charge snapshot. Ties between events in the same second go to the snapshot with the larger `amount_refunded`.
- Deleted Stripe customers are removed (`apply_as_deletes`).
- Websites are normalized to a domain: `https://www.Harbor.com/` becomes `harbor.com`.
**Bad records are quarantined, not dropped.** Charges that break a rule (missing ID, non-positive amount, unknown status) go to `silver.stripe_charge_quarantine`, where they can be inspected without blocking the pipeline.
 
### Gold
 
**Silver and gold deduplicate different things.** Silver removes repeated copies of the *same* Salesforce record. Gold resolves *different* records that represent the same company: accounts sharing a normalized domain are one company, and the oldest record is the master (12 records → 8 companies).
 
**Joins are designed not to lose or double-count money.**
- Stripe customers are matched to `dim_account`, which has exactly one row per domain, so a payment can never match a company twice.
- Left and full outer joins keep customers missing from the CRM and companies with no payments.
- A singular test, `assert_gold_collected_matches_silver`, fails the build if gold's collected total differs from silver's by more than a cent.
### Security
 
**Analysts see gold only.** Terraform grants `USE_CATALOG` on the catalog and `USE_SCHEMA` + `SELECT` on `gold`. Raw, bronze, silver, and intermediate stay private.
 
**Credentials never enter the repo.** Locally they live in a gitignored `.env`; in GitHub Actions they come from encrypted repository secrets. CI uses placeholder credentials on purpose, because neither the unit tests nor `dbt parse` connects to anything.
 
**Stripe scripts refuse live keys.** The extractor and seeder exit unless `STRIPE_API_KEY` starts with `sk_test_`.
 
## Automation
 
| Workflow | When | What it does |
|---|---|---|
| `ci.yml` | Every pull request and push to `main` | Unit tests and `dbt parse` on a clean runner (Python 3.12) |
| `refresh.yml` | Daily, plus on demand | Extract Salesforce → extract Stripe → run the Lakeflow pipeline and wait → `dbt build` with all data tests |
 
Steps stop at the first failure, so dbt never builds on top of a failed pipeline run, and a failed data test turns the run red. `main` is protected: changes need a pull request with passing CI, and force pushes are blocked.
 
## Problems solved along the way
 
The full log is in [`DEVLOG.md`](DEVLOG.md). Highlights:
 
- **Salesforce rejected correct credentials** with `INVALID_LOGIN`. The org's Login History showed the real cause, "SOAP Login Disabled," so the extractors use OAuth client credentials through an External Client App.
- **Free Edition limits:** catalogs can't be created through the API, and API-created groups are workspace-local, which Unity Catalog grants can't use. The catalog is created in the UI and grants go to the built-in `account users` group; everything else stays in Terraform.
- **Raw Stripe files went missing.** Rerunning the extractor did nothing, because the watermark said those events were done. Backfilled by resetting the Stripe watermark and re-extracting; the duplicate charges this produced were removed by silver's upserts.
- **An accidental second pipeline had claimed tables.** A table can belong to only one pipeline, so ownership was moved back with `ALTER STREAMING TABLE ... SET TBLPROPERTIES ('pipelines.pipelineId' = ...)`.
- **CI broke when GitHub's runners dropped Python 3.9.** CI moved to 3.12 and the runner image is pinned, so environment changes happen deliberately.
## Seed data
 
The seed scripts create a small, deliberately messy dataset, so the gold layer has real problems to catch:
 
| Scenario | Example |
|---|---|
| Duplicate accounts with messy names and URLs | `Harbor Analytics`, `Harbor Analytics Inc.`, `HARBOR ANALYTICS` |
| Won deals whose amount differs from Stripe collections | Harbor Analytics, Brightline Logistics, Atlas Robotics |
| Won deal, never paid | Keystone Legal |
| Open deal that shouldn't count as booked | Orbit Media Group (Prospecting) |
| Opportunity attached to a duplicate account | `HARBOR ANALYTICS`, $500 |
| Paying customers with no Salesforce account | Lumen Coffee, Quarry Fitness |
 
> The seed scripts are **not idempotent**. Running one twice creates a second full set of records.
 
## Setup
 
### Prerequisites
 
- Databricks workspace with Unity Catalog (built and tested on **Free Edition**) and a SQL warehouse
- Salesforce dev org with an **External Client App** (OAuth client credentials)
- Stripe account in **test mode**
- Python 3.9+ (CI uses 3.12), Terraform, and dbt (`dbt-databricks`)
### 1. Infrastructure
 
Free Edition uses Databricks-managed default storage, so the catalog can't be created through the API. Create a catalog named `revenue` in the UI first, then run:
 
```bash
terraform init
terraform apply
```
 
The `landing_volume_path` output is the value for `LANDING_VOLUME` below. Defaults suit Free Edition: `create_catalog = false`, and grants go to the built-in `account users` group.
 
### 2. Environment variables
 
Put these in a gitignored `.env`:
 
| Variable | Used by |
|---|---|
| `DATABRICKS_HOST`, `DATABRICKS_TOKEN` | Terraform, volume client, pipeline trigger, dbt |
| `DATABRICKS_HTTP_PATH` | dbt (your SQL warehouse's HTTP path) |
| `LANDING_VOLUME` | Extractors (for example, `/Volumes/revenue/raw/landing`) |
| `SF_CLIENT_ID`, `SF_CLIENT_SECRET`, `SF_DOMAIN` | Salesforce extract and seed |
| `STRIPE_API_KEY` | Stripe extract and seed (must be `sk_test_...`) |
 
For the scheduled workflow, add the same values (except `LANDING_VOLUME`) as **repository secrets** under Settings → Secrets and variables → Actions.
 
### 3. Install, seed, and extract
 
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
set -a && source .env && set +a
 
# One-time seed (order matters: opportunities look up the seeded accounts)
python -m extract.seed
python -m extract.seed_opportunities
python -m extract.stripe_seed
 
# Incremental extracts (safe to rerun)
python -m extract.salesforce_extract
python -m extract.stripe_extract
```
 
### 4. Pipeline
 
Create a Lakeflow Declarative Pipeline in Databricks with `pipelines/medallion.py` as its source and run it. It builds the four bronze tables, the four silver tables, and the charge quarantine table.
 
### 5. Gold
 
```bash
cd dbt
dbt build --profiles-dir .
```
 
This runs the source tests, builds the intermediate views and gold tables, and runs every data test, including the reconciliation check.
 
## Tests
 
```bash
pytest
```
 
The unit tests cover the record envelope and landing paths, watermark persistence, and Stripe event grouping. They use an in-memory fake volume, so they need no credentials. Data tests live in dbt and run with `dbt build`.
 
## Possible next steps
 
- Declare explicit bronze schemas, so an empty source folder can't fail the pipeline, and the schema becomes a data contract.
- Collapse the four silver tables into a shared `make_silver()` helper with a quarantine table for each.
- Propagate Salesforce deletions (`IsDeleted`).
- Fuzzy name matching for accounts without a website.
- Move orchestration to Airflow triggering Databricks Jobs, for per-task retries and backfills.
 