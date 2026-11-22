# Working on the desk tool

Keep one change per pull request. Aim for fewer than 300 changed lines so someone can read it carefully. Use `fix/<short-name>`, `feat/<short-name>`, `docs/<short-name>` or `chore/<short-name>` for a branch. Write commit messages in the imperative and keep the subject under 72 characters. For example: `Fix the return date comparison`.

Run `python -m pytest` and `python -m ruff check .` before asking for review. Explain the command you tried and what it printed. If a business rule changes, update its policy text with Huda Al-Mansoori. Do not edit or delete existing tests or workflow files. Put new checks where the issue says. Ask Mira Saad if a test looks wrong.

Start each review comment with a label:

- **issue**: must be fixed before merging.
- **suggestion**: worth doing; the author decides.
- **question**: asks for an explanation.
- **nit**: a small style point.
- **praise**: calls out something useful.

The author answers every comment, including suggestions they decline. Squash merge after review and passing checks. Delete the branch after merging.

Karim Haddad owns releases and the changelog. Yousef Darwish reviews the rules, database and client interface. Sana Barakat owns onboarding and the command-line and HTTP entry points. Mira Saad owns test and sample-data quality. Contact a teammate at `first.last@bayline.example` using their name; Huda's handle is `huda.al-mansoori@bayline.example`.
