# 0001: SQLite, standard library and integer money

Date: 2026-04-19
Status: Accepted
Decided by: Yousef Darwish and Karim Haddad

## Context

The desk needs a small local database that is easy to copy and inspect. The old price script used floats; adding 0.1 and 0.2 did not produce an exact decimal amount.

## Decision

Use a SQLite file with foreign keys enabled. Prefer the Python standard library. Store all money as whole piastres, with 100 piastres to 1 EGP. Convert decimal input at the boundary and format amounts only for display.

## Consequences

Fees compare exactly. One transaction covers each desk action. SQLite serializes writes, so keep transactions short. The schema carries explicit constraints; no ORM is involved.
