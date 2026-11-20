# 0004: Assist calls the model seam

Date: 2026-11-20
Status: Accepted
Decided by: Yousef Darwish and Lina Haddad

## Context

The support desk needs help reading customer messages. Rules must remain independent of model responses.

## Decision

Code in `assist` may call the model through `bayline.llm`. Rules may not import `llm` or `assist`.

## Consequences

Message helpers can use replay and recording clients. Business rules remain independent of the model.
