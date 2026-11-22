# First day on Customer Platform

Start with the README setup for your system. Create the virtual environment, install the package, and run `python -m bayline seed`. Then run `python -m pytest` and `python -m ruff check .`. The tests need neither a network connection nor a provider key.

Look up `BYL260411871`. Check its return at `2026-10-24T19:40:00Z`; the answer should be day 30 and allowed. Read `docs/policies/returns-policy.md`, `src/bayline/rules/returns.py` and `tests/test_returns.py` together. Read `docs/architecture.md` and `docs/data-model.md` before changing a write path.

Sana Barakat is the first contact for setup and command-line questions. Yousef Darwish reviews business rules and database changes. Mira Saad handles tests and sample records. Huda Al-Mansoori approves policy wording. Karim Haddad owns releases.

Use a small branch and one pull request per change. Read `CONTRIBUTING.md` before sending it for review. Keep local databases under `var/`; never include a provider key or customer contact details in an issue.
