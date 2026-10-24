# Huginn agent instructions

Read `CLAUDE.md` for adopted code/design standards and verification commands, and
the relevant sections of `docs/architecture.md` before changing a layer.

## Organization is a requirement

1. Follow the responsibility separation already used by management, matchmaking,
   pipeline control, and the ELT repository directories. Do not collect models,
   policies, persistence, orchestration and CLI/UI in a flat feature/ticket/phase
   directory. Small features and initial versions follow the same rule.
2. Within ELT, place values in `models/`, aliases in `types/`, version constants
   in `constants/`, pure decisions in `policies/`, source parsing in
   `normalizers/`, concrete database adapters in `repositories/`, repository
   Protocols in `repositories/protocols/`, orchestration in `services/`, and
   CLI/serialization in `presentation/`. Reuse an existing owning area.
3. Use focused modules, normally one public model or repository class per file.
   Models, normalizers and policies must not import database/network clients,
   concrete repositories or presentation. Services depend on repository Protocols;
   CLI/composition selects concrete implementations. Separate infrastructure IO
   from pure decisions and report construction.
4. Mirror these responsibility boundaries in tests. Review the changed file tree
   and import direction, including delegated work, before calling a task done.
   Test behavior and meaningful architecture boundaries. Remove obsolete mixed
   packages rather than hiding them behind re-export facades.

## Working constraints

1. Prefix shell commands with `rtk`, per the global RTK instructions.
2. Preserve other worktrees and unrelated user changes. Use the scoped branch;
   never reset the dirty primary checkout or commit directly to master.
3. Keep plans, task checklists, handoffs, extracted rows, review reports and local
   runtime artifacts under ignored local storage. Do not commit them. Operator
   docs and this intentional repository instruction file are tracked.
4. Tests use harness-owned disposable PostgreSQL. Never initialize/reset the
   persistent database, run migrations or perform a backfill as a side effect.
5. Run the relevant tests, `uv run ruff check .`, and
   `uv run ruff format --check .`. Respect the repository commit/push hooks.

## Code review rules

Flag mixed-responsibility feature packages and imports from core models/policies
into concrete persistence, network clients or presentation. Move code to its
owning responsibility and preserve dependency direction; a passing functional
test suite alone does not establish architectural correctness.
