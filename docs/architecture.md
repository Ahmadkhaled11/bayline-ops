# How the tool fits together

The CLI accepts a command, reads records through `repository.py`, and passes them to a rule. Rules take time as an argument. They do not read the clock, open a database or call a model. `status.py` uses event time and then event id to choose the current status. Checks ignore events after the requested time.

| Module | Responsibility |
| --- | --- |
| `models` | Frozen records and enumerations |
| `timeutil`, `business_days`, `geography`, `money`, `tracking_numbers` | Shared conventions |
| `rules` | Prices, promises, delays, returns, claims and address decisions |
| `db`, `schema.sql` | Connections, constraints and transactions |
| `repository` | Read queries and summaries |
| `services` | Atomic decisions and writes |
| `cli` | Argument handling, output and exit codes |
| `web` | Read-only WSGI JSON routes |
| `policies` | Markdown documents by slug |
| `sample` | Seed generation, input validation and canonical checksums |
| `llm` | Replay, live and recording clients behind one contract |

Rules import only the domain records and shared calculation helpers, plus other rule modules. They never import `db`, `repository`, `llm`, `assist` or `sample`. Operational writes go through services; the seed loader handles initial loading. The HTTP service uses SQLite's query-only setting and has no write routes. The message helper calls the model clients through their interface.

The seed command validates all authored messages before replacing a database. It writes a sibling staging file, closes it, and then replaces the destination. An existing database needs `--force`. The canonical checksum sorts tables and primary keys, then hashes compact UTF-8 JSON lines; it does not hash SQLite's physical file layout.

Services record refused decisions as well as allowed ones. An address update, its case and its event share one transaction. A reply and the message status update share another. SQLite foreign keys remain enabled. A failed write rolls the transaction back.

Snapshot records describe their stored state. Event status can be checked at a supplied time, but a customer record or an address field is not a full version history. Return, claim and address records later than the check time are ignored by rules.

The `assist` package builds requests for customer messages and returns raw model replies.

The `evals` package collects replies and scores their primary topics against authored labels.
