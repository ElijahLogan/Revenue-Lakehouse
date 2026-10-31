"""Seed Stripe test mode with customers and payments.

Customers input into Stripe
6 match emails in salesforce. 2 only in stripe 
2 companies never pay 

"""

from __future__ import annotations

import os

import stripe

from extract.seed import COMPANIES

STRIPE_ONLY = [("Lumen Coffee", "lumencoffee.com"), ("Quarry Fitness", "quarryfit.com")]

# Amounts in cents, as Stripe expects. One list of charges per customer.
CHARGES = [[200000], [100000, 100000], [400000], [200000, 200000, 200000], [100000], [400000, 100000]]


def run() -> None:
    stripe.api_key = os.environ["STRIPE_API_KEY"]
    if not stripe.api_key.startswith("sk_test_"):
        raise SystemExit("Refusing to run: STRIPE_API_KEY must be a test-mode key.")

    paying = [(name, website) for name, website, _city, _state in COMPANIES[:6]] + STRIPE_ONLY
    for i, (name, website) in enumerate(paying):
        customer = stripe.Customer.create(name=name, email=f"accounts@{website}")
        for amount in CHARGES[i % len(CHARGES)]:
           stripe.PaymentIntent.create(
                amount=amount,
                currency="usd",
                customer=customer.id,
                payment_method="pm_card_visa",  # Stripe's built-in test card
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                confirm=True,
            )
    print(f"Created {len(paying)} Stripe customers with test payments")


if __name__ == "__main__":
    run()