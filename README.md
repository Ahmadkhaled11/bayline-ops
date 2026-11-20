# Bayline operations

`bayline-ops` is the internal parcel operations tool for Bayline Cargo. The desk uses it to look up shipments, check returns and claims, change delivery addresses, and record customer replies. Records live in a local SQLite file. Prices use whole piastres. Rules use the time supplied by the caller.

## Set up

Use Python 3.11 or newer. Run these commands from this folder.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

macOS and Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

No activation script is needed. Load the sample database, run the tests, and start the read-only HTTP service.

Windows PowerShell:

```powershell
.venv\Scripts\python -m bayline seed
.venv\Scripts\python -m pytest
.venv\Scripts\python -m bayline serve
```

macOS and Linux:

```sh
.venv/bin/python -m bayline seed
.venv/bin/python -m pytest
.venv/bin/python -m bayline serve
```

In the commands below, replace `python` with the virtual environment path shown above.

The service listens at `http://127.0.0.1:8080`. Try `/shipments/BYL260411871` or `/health`. It accepts GET requests only. Stop it with Ctrl+C. Run `python -m ruff check .` before review.

## Desk commands

```sh
python -m bayline shipment BYL260411871
python -m bayline return-check BYL260411871 --at 2026-10-24T19:40:00Z
python -m bayline messages --status new --limit 10
python -m bayline policy returns-policy
python -m bayline checksum
```

Every command accepts `--db PATH` and `--json`. The database defaults to `BAYLINE_DB`, then `var/bayline.db`. Checks default to the snapshot's time, 2 November 2026 at 09:00 Cairo, rather than today's date. Use `--at` to check another UTC time. Exit codes are 0 for success, 1 for a refused decision, 2 for bad input, 3 for a missing record, and 4 for a missing or empty database. A refused write is still recorded. `seed --force` replaces the sample database; it does not merge records.

| Folder | Contents |
| --- | --- |
| `src/bayline` | Models, database access, CLI and HTTP service |
| `src/bayline/rules` | Pure business rules |
| `src/bayline/sample` | Repeatable sample data and validation |
| `src/bayline/llm` | Isolated client interface; operations do not use it |
| `src/bayline/assist` | Message helper requests |
| `evals` | Topic scoring and reports |
| `tests` | Rules, workflows and data checks |
| `data/authored` | Maintained customer messages |
| `docs` | Team notes and policies |
| `var` | Local database files; not tracked |

Policies live in `docs/policies`, owned by Customer Service. `BAYLINE_DOCS_DIR` can select another document root. The variables listed in `.env.example` are optional settings; the tool never loads a `.env` file. Model mode defaults to replay, which makes no network request. `llm-check` reports configuration without showing a key. Only an explicit `llm-check --ping` in live mode sends a small request.

The repository moved to GitHub in November 2026; earlier history stays on the old internal server.
