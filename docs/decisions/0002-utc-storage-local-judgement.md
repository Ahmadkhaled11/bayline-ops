# 0002: Store UTC and judge local dates

Date: 2026-02-01
Status: Accepted
Decided by: Yousef Darwish and Huda Al-Mansoori

## Context

A customer can be on a different calendar date from the desk. Fixed offsets also gave the wrong date when Egypt's summer time ended.

## Decision

Store UTC timestamps with a trailing Z. Use `zoneinfo` for local dates. Pickup cut-offs use Africa/Cairo. Return and claim windows use the delivery address time zone. Rules take `at` as an argument; they never read the clock.

## Consequences

The same input gives the same decision. Tests cover the 2026 clock change and a Dubai request crossing midnight. The CLI defaults to the database snapshot time and accepts an explicit UTC time for a different check.
