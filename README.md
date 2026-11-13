# Revenue Lakehouse

A revenue data lakehouse on **Databricks** that brings together **Salesforce** (what sales says was won) and **Stripe** (what customers actually paid). The goal is a gold layer that reconciles the two: bookings vs. collections, deals won but never paid, customers that only exist in billing, and duplicate accounts that inflate the numbers.

> **Status: work in progress.** Infrastructure, extraction, bronze, and silver for Salesforce accounts are built. Silver for the remaining sources, entity matching, and gold marts (dbt) are next. See [Roadmap](#roadmap).

## Architecture

```
Salesforce (Accounts, Opportunities)      Stripe (Events API: customers, charges)
              │                                          │
              └──────────── Python extractors ───────────┘
                         incremental, watermark-based
                                     │
                                     ▼
          raw     /Volumes/revenue/raw/landing   NDJSON, one file per run, never overwritten
                                     │  Auto Loader
                                     ▼
          bronze  revenue.bronze.*                raw records as landed, plus file lineage
                                     │  Lakeflow Declarative Pipeline
                                     ▼
          silver  revenue.silver.*                typed, validated, one row per entity
                                     │  dbt (planned)
                                     ▼
    intermediate  revenue.intermediate.*          entity resolution, Salesforce↔Stripe matching
                                     │
                                     ▼
          gold    revenue.gold.*                  business marts: the only layer analysts can read
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
| `pipelines/medallion.py` | Lakeflow Declarative Pipeline (formerly DLT): bronze for all sources, silver for Salesforce accounts |
| `notebooks/01_bronze_salesforce_account.py` | Earlier standalone Auto Loader notebook for one bronze table, kept for reference |
| `tests/` | Unit tests for records, watermarks, and Stripe event grouping |
| `DEVLOG.md` | Running log of problems hit and how they were solved |

## Design decisions

**Raw data is append-only.** Each run writes a new file at `<source>/<entity>/run_date=YYYY-MM-DD/<run_id>.json`. Nothing in the landing volume is overwritten, so any layer can be rebuilt from raw.

**Every record carries lineage.** Records are landed as NDJSON wrapped in an envelope:

```json
{"_source": "salesforce", "_entity": "account", "_run_id": "2026-10-31T03-36-31Z",
 "_extracted_at": "2026-10-31T03:36:31Z", "payload": { ... }}
```

Bronze adds `_file_path` and `_ingested_at`, so every row can be traced to the file and run that produced it.

**Extracts are incremental.**
- *Salesforce* filters on `SystemModstamp > <watermark>`. The first run uses `1970-01-01` and pulls everything.
- *Stripe* reads the **Events API** instead of list endpoints. List endpoints filter on creation date, so they miss later changes like a refund on an old charge. Events capture every change. The watermark is the newest event's `created` timestamp.
- Watermarks are held in memory and **saved only after every file has landed**, so a failed run is re-pulled instead of skipped.
- Runs that find no changes write no files.

**Silver keeps the latest version of each record.** `apply_changes` (SCD type 1) keys on `account_id` and sequences by `modified_at`, with `_file_path` breaking ties between identical copies from repeated pulls. Data quality expectations drop rows without an ID and flag rows without a name.

**Websites are normalized to a domain.** `https://www.Harbor.com/` becomes `harbor.com`. This is the join key for collapsing duplicate accounts and matching Salesforce accounts to Stripe customers by email domain.

**Analysts see gold only.** Terraform grants `USE_CATALOG` on the catalog and `USE_SCHEMA` + `SELECT` on `gold`. Raw, bronze, silver, and intermediate stay private.

**Stripe scripts refuse live keys.** The extractor and seeder exit unless `STRIPE_API_KEY` starts with `sk_test_`.

## Seed data

The seed scripts create a small, deliberately messy dataset, so the gold layer has real problems to catch:

| Scenario | Example |
|---|---|
| Duplicate accounts with messy names and URLs | `Harbor Analytics`, `Harbor Analytics Inc.`, `HARBOR ANALYTICS`, `https://www.harboranalytics.com` |
| Won deals whose amount differs from Stripe collections | Several of the 6 paying companies |
| Won deal, never paid | Keystone Legal |
| Open deal that shouldn't count as booked | Orbit Media Group (Prospecting) |
| Opportunity attached to a duplicate account | `HARBOR ANALYTICS`, $500 |
| Paying customers with no Salesforce account | Lumen Coffee, Quarry Fitness |

> The seed scripts are **not idempotent**. Running one twice creates a second full set of records.

## Setup

### Prerequisites

- Databricks workspace with Unity Catalog (built and tested on **Free Edition**)
- Salesforce dev org with an **External Client App** (OAuth client credentials)
- Stripe account in **test mode**
- Python 3.10+, Terraform, and the Databricks CLI

### 1. Infrastructure

Free Edition uses Databricks-managed default storage, so the catalog can't be created through the API. Create a catalog named `revenue` in the UI first, then run:

```bash
terraform init
terraform apply
```

The `landing_volume_path` output is the value for `LANDING_VOLUME` below.

Defaults suit Free Edition: `create_catalog = false`, and grants go to the built-in `account users` group, because Free Edition can't create account-level groups.

### 2. Environment variables

Put these in a gitignored `.env`, and put Databricks credentials in `~/.databrickscfg`:

| Variable | Used by |
|---|---|
| `DATABRICKS_HOST`, `DATABRICKS_TOKEN` | Terraform and volume client |
| `LANDING_VOLUME` | Extractors (for example, `/Volumes/revenue/raw/landing`) |
| `SF_CLIENT_ID`, `SF_CLIENT_SECRET`, `SF_DOMAIN` | Salesforce extract and seed |
| `STRIPE_API_KEY` | Stripe extract and seed (must be `sk_test_...`) |

### 3. Install, seed, and extract

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# One-time seed (order matters: opportunities look up the seeded accounts)
python -m extract.seed
python -m extract.seed_opportunities
python -m extract.stripe_seed

# Incremental extracts (safe to rerun)
python -m extract.salesforce_extract
python -m extract.stripe_extract
```

### 4. Pipeline

Create a Lakeflow Declarative Pipeline in Databricks with `pipelines/medallion.py` as its source, then run it. It creates the bronze tables for all four source entities and `revenue.silver.salesforce_account`.

## Tests

```bash
pytest
ruff check .
```

The tests cover the record envelope and landing paths, watermark persistence, and Stripe event grouping. They use an in-memory fake volume, so they need no credentials.

## Roadmap

- [x] Terraform: catalog schemas, landing volume, gold-only grants
- [x] Incremental Salesforce extract (Accounts, Opportunities)
- [x] Incremental Stripe extract via Events (customers, charges)
- [x] Bronze for all sources with Auto Loader
- [x] Silver: Salesforce accounts
- [ ] Silver: Salesforce opportunities, Stripe customers and charges
- [ ] dbt intermediate: account deduplication and Salesforce↔Stripe matching by domain
- [ ] dbt gold: bookings vs. collections variance mart
- [ ] GitHub Actions schedule for the extractors
