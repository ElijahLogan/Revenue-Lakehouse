"""Seed with realistic, messy accounts.


Run once: running it again creates another full set.
"""

from __future__ import annotations

from extract.salesforce_extract import connect

COMPANIES = [
    ("Harbor Analytics", "harboranalytics.com", "New York", "NY"),
    ("Brightline Logistics", "brightlinelogistics.com", "Newark", "NJ"),
    ("Cedar & Pine Studio", "cedarpine.co", "Brooklyn", "NY"),
    ("Northwind Health", "northwindhealth.org", "Boston", "MA"),
    ("Atlas Robotics", "atlasrobotics.io", "Pittsburgh", "PA"),
    ("Juniper Foods", "juniperfoods.com", "Philadelphia", "PA"),
    ("Keystone Legal", "keystonelegal.com", "Albany", "NY"),
    ("Orbit Media Group", "orbitmedia.com", "Jersey City", "NJ"),
]

# Messy variants of real accounts: different casing, suffixes, URL formats.
DUPLICATES = [
    ("Harbor Analytics Inc.", "https://www.harboranalytics.com", "New York", "NY"),
    ("HARBOR ANALYTICS", "harboranalytics.com/", "NYC", "NY"),
    ("Brightline Logistics LLC", "www.brightlinelogistics.com", "Newark", "NJ"),
    ("Atlas Robotics, Inc", "http://atlasrobotics.io", "Pittsburgh", "PA"),
]

# Salesforce's default duplicate rules would block the deliberate duplicates.
# This header tells Salesforce to save them anyway.
ALLOW_DUPLICATES = {"Sforce-Duplicate-Rule-Header": "allowSave=true"}


def run() -> None:
    sf = connect()
    for name, website, city, state in COMPANIES + DUPLICATES:
       sf.Account.create(
    {
        "Name": name,
        "Website": website,
        "BillingCity": city,
        "BillingStateCode": state,      
        "BillingCountryCode": "US",
    },
    headers=ALLOW_DUPLICATES,
)
    print(f"Created {len(COMPANIES) + len(DUPLICATES)} accounts ({len(DUPLICATES)} deliberate duplicates)")


if __name__ == "__main__":
    run()