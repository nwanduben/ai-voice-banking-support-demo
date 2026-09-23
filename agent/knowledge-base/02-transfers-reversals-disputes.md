# Transfers, Pending Transactions, Reversals and Disputes

## Transfer statuses explained
- **Successful**: the money left your account and the receiving bank confirmed the credit. If the recipient still can't see it, they should check with their own bank using the session reference.
- **Pending**: the transfer is still being processed between banks. This usually clears within minutes, but it can take longer when bank networks are busy.
- **Failed, not debited**: nothing left your account. You can try again.
- **Failed, debited**: the money left your account but didn't reach the recipient. It will be reversed to you automatically.
- **Reversed**: the money has been returned to your account.

## How long refunds should take (CBN timelines)
The Central Bank of Nigeria set these maximum timelines for resolving failed electronic transactions, effective 8 June 2020:
- ATM withdrawal at an ENTIN ATM (on-us) with no cash dispensed: reversed instantly.
- ATM withdrawal at another bank's ATM (not-on-us) with no cash dispensed: within 48 hours.
- Failed POS transactions: within 72 hours.
- Failed online transfers: within 72 hours.

Source: CBN revised timelines for dispense errors and refund complaints, reported by Nairametrics on 31 May 2020: https://nairametrics.com/2020/05/31/just-in-cbn-revises-timelines-for-resolution-of-dispense-errors-refund-complaints/

Note: in 2025 the CBN exposed draft ATM guidelines that would require instant on-us reversals (manual within 24 hours if automatic fails) and 48 hours for not-on-us. Treat these as a draft until confirmed. https://www.vanguardngr.com/2025/10/cbn-orders-banks-to-refund-failed-atm-transactions-within-48-hours/

## What ENTIN does
- If a debited transfer hasn't been credited or reversed within the CBN timeline, ENTIN logs a complaint and escalates it.
- For ATM no-cash and POS problems, ENTIN logs a dispute. The customer gets a reference that starts with D S P.
- Disputes on another bank's ATM are resolved together with that bank.
- Amounts of 1,000,000 naira or more, and issues reported three or more times in a week, go straight to a senior colleague.

## ATM cash not dispensed: what to tell the customer
Keep the ATM receipt if you have one. Note the ATM location and time. Don't try the same withdrawal again repeatedly.

## POS double debit
If you were charged twice, keep the merchant receipt. ENTIN will investigate the second debit.

## I don't know the transaction reference
That's fine. The assistant can find it using the approximate date, amount and type of transaction.
