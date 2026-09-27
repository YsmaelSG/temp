# Design Spec: Transfers Between Accounts (extra design practice)

**Status:** Draft · **Owner:** Ledger team

## Background

Users often move money from checking to savings. Today they have to create
a debit on one account and a matching credit on the other, and if the second
request fails, their money "disappears." We want a first-class transfer
operation.

## Requirements

1. A user can transfer an amount from one of their accounts to another.
2. A transfer produces a debit on the source account and a credit on the
   destination account. Either both happen, or neither does.
3. A transfer cannot overdraw the source account.
4. Both accounts must use the same currency.
5. Mobile clients retry on flaky networks, and a retry must never move money
   twice.
6. Users can see their past transfers, and from a single transaction they can
   tell whether it was part of a transfer.

## Constraints

- Existing transaction endpoints and response shapes must keep working.
- Transactions remain immutable. A mistaken transfer is undone with a
  reverse transfer, not by editing or deleting anything.
