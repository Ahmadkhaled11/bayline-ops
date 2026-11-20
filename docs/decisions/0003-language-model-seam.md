# 0003: One model client contract

Date: 2026-11-12
Status: Accepted
Decided by: Yousef Darwish and Lina Haddad

## Context

Provider-specific clients make tests depend on credentials and network access. The operations rules must remain independent of providers.

## Decision

Use one small request and response interface. Replay files supply test responses without a key. A live implementation uses standard-library HTTP with an injectable transport. Configuration comes only from named environment variables. Do not add provider SDKs.

## Consequences

Replay is the default. Recording refuses to overwrite a saved response. The live client makes one request and has no retries, caching or streaming. Operations do not call this interface. `llm-check` reports settings; `--ping` makes one small request only in live mode.
