"""Seed won and open opportunities
the seeded Salesforce accounts.

Some won amounts match what Stripe collected, some don't
, and one company has a
won deal but never paid, 
variance in gold account
"""

from __future__ import annotations

from extract.salesforce_extract import connect

# Account name -> (stage, amount in dollars)
OPPORTUNITIES = {
    "Harbor Analytics": ("Closed Won", 2000),
    "Brightline Logistics": ("Closed Won", 3000),
    "Cedar & Pine Studio": ("Closed Won", 4000),
    "Northwind Health": ("Closed Won", 6000),
    "Atlas Robotics": ("Closed Won", 2400),
    "Juniper Foods": ("Closed Won", 5000),
    "Keystone Legal": ("Closed Won", 1200),     # won but never paid in Stripe
    "Orbit Media Group": ("Prospecting", 8000),  # open deal, not booked yet
    "HARBOR ANALYTICS": ("Closed Won", 500),      # on a duplicate account record
}


def run() -> None:
    sf = connect()
    accounts = sf.query_all("SELECT Id, Name FROM Account")["records"]
    ids_by_name = {a["Name"]: a["Id"] for a in accounts}

    for account_name, (stage, amount) in OPPORTUNITIES.items():
        sf.Opportunity.create(
            {
                "AccountId": ids_by_name[account_name],
                "Name": f"{account_name} - Annual Plan",
                "StageName": stage,
                "Amount": amount,
                "CloseDate": "2026-10-31",
            }
        )
    print(f"Created {len(OPPORTUNITIES)} opportunities")


if __name__ == "__main__":
    run()