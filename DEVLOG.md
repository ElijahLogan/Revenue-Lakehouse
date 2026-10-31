# Dev log

## 2026-10-29 — Infrastructure (Terraform + Unity Catalog)

- **Catalog creation failed:** "Metastore storage root URL does not exist." Free Edition uses
  Databricks-managed Default Storage, so catalogs can't be created through the API. Created
  `revenue` in the UI and set `create_catalog = false`.
- **Grants failed:** "Could not find principal." Groups created through the workspace API are
  workspace-local; Unity Catalog grants need account-level groups. Granted gold-only access to
  the built-in `account users` group instead.
- **Credentials kept disappearing:** `export` only lasts one terminal session. Moved them into
  `~/.databrickscfg` and a gitignored `.env`.

## 2026-10-30 — First extract

- **Salesforce login failed with INVALID_LOGIN** even with correct credentials. Login History
  showed the real cause: "SOAP Login Disabled." Switched to OAuth client credentials through an
  External Client App. Lesson: when an error is vague, find where the system logs the real reason.
- **Seed failed:** "A country/territory must be specified..." The org enforces state/country
  picklists, so I send `BillingStateCode` and `BillingCountryCode`.
- **Empty files:** a run with 0 records still wrote a file. Added a guard to skip the write.

## 2026-10-31 — Incremental extract with watermarks

- Run 1: 12 accounts changed since 1970-01-01 (first run pulls everything).
- Run 3: 0 accounts changed. The watermark works.
- Run 4: [fill in after editing one account]
- **Bug in my own code:** compared `resp.status_code == '404'` (a string) instead of `404` (an int),
  so the first-run 404 crashed instead of returning None.
- Expected Salesforce's timestamp format (`.000+0000`) to break the SOQL query on the second run.
  Tested it, and SOQL accepted it, so no fix was needed.
