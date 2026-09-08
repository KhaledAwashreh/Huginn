# Python best practices

This is the general Python reference: what the language's own community and
tooling ecosystem consider good practice in 2026, researched rather than
assumed, sourced at the bottom. It exists so you (or anyone reviewing an
implementation agent's work on this repo) has a concrete standard to check
against, not a vague sense that "this looks fine."

`CLAUDE.md` is the other half: it records which of these general practices
Huginn has actually adopted, and the project-specific decisions layered on
top (frozen dataclasses, Protocol-first ports, the medallion layering, and so
on). Where the two overlap, `CLAUDE.md` wins, it is the more specific,
already-settled word on this codebase. This document is where those settled
choices came from, and where anything not yet decided for Huginn is flagged
as such.

## 1. Style and formatting

Python's own style guide is PEP 8: 4-space indentation (never tabs), a line
length around 79-88 characters, `snake_case` for functions and variables,
`PascalCase` for classes, `UPPER_CASE` for constants, two blank lines between
top-level definitions.

Nobody applies PEP 8 by hand anymore. The 2026 standard tool is **Ruff**: one
fast linter and formatter that has absorbed what used to be three separate
tools (Black for formatting, isort for import ordering, Flake8 for linting).
`ruff format` fixes style automatically; `ruff check` catches the rest.
Huginn has decided on Ruff (ADR-0004) but deliberately has not installed or
configured it yet, low priority for now.

## 2. Type hints and type checking

A type hint (`def fetch(source: str) -> list[RawRecord]:`) is documentation
that a machine can check. It doesn't change what the code does at runtime,
but it lets a separate tool catch a whole class of bugs (passing the wrong
kind of value, forgetting a `None` case) before the code ever runs.

Huginn already writes type hints everywhere (see any file under `src/`).
What's missing is a type *checker* actually running against them. Decided:
**pyright** over mypy (ADR-0004). Not yet installed or configured,
deliberately deferred, low priority right now.

Modern syntax note: use `list[str]`, `dict[str, int]`, `X | None`, not the
older `List[str]`, `Optional[X]` from the `typing` module. Huginn's code
already does this correctly throughout.

## 3. Docstrings

PEP 257 sets the baseline: triple double quotes, a one-line summary that
fits on its own line, a blank line, then further detail if needed. Beyond
that baseline, most teams pick a further convention (Google style is the
most common: `Args:`, `Returns:`, `Raises:` sections). Huginn does not use
that section-based format; it uses prose docstrings that cite the
architecture document or an ADR by name (see `CLAUDE.md`, code standards
point 3). That's a deliberate deviation from the Google-style default, kept
consistent throughout, not an oversight.

## 4. Project structure

The current standard shape for a Python project: a `src/` layout (the
package lives in `src/<package_name>/`, not at the repository root), a
`tests/` directory mirroring it, and `pyproject.toml` as the single
configuration file for build metadata, dependencies, and tool settings. This
replaces the older `setup.py`/`setup.cfg` split entirely.

The reason for `src/` specifically: without it, Python can accidentally
import your working directory's copy of the code instead of the properly
installed package, which hides packaging bugs until they show up somewhere
that isn't your laptop. Huginn already uses this layout correctly
(`src/huginn/`, `tests/`, one `pyproject.toml`).

## 5. Dependency management

Huginn uses `uv`, the current fastest and most complete option (it replaces
`pip`, `pip-tools`, `virtualenv`, and `poetry`-style project management with
one tool). The practices that matter regardless of which tool a project
uses:

1. Keep `uv.lock` committed to version control. It's a fully resolved,
   hashed snapshot of the entire dependency tree, what guarantees "works on
   my machine" also works on any other machine.
2. Keep production and development dependencies separate (`uv add` vs.
   `uv add --dev`). A production build should never need `pytest` installed.
   Huginn already does this correctly (`[dependency-groups] dev = [...]` in
   `pyproject.toml`).
3. Update dependencies deliberately, not accidentally. Run the full test
   suite after any dependency bump before trusting it.

## 6. Error handling and logging

Huginn requires logging instrumentation from day one, not deferred (ADR-0005).
A few concrete rules, since this is the area where "looks fine" most often
isn't:

1. **Never catch an exception and do nothing with it.** Silently swallowing
   an error (an empty `except:` block, or one that only `pass`es) is called
   "error hiding," and it's one of the most common causes of a system that
   fails quietly and nobody notices until the damage is done. This isn't
   abstract for Huginn: it's the exact same principle already
   architecturally encoded in the arch document's "a job that has silently
   stopped running" concern (section 4.1) and this session's own null-id
   resolution for the HN adapter, the general rule is: a real failure must
   surface somewhere, always.
2. **Log an exception once, at the point that actually handles it**, not
   once when it's caught and again when it's re-raised (the "log and throw"
   anti-pattern, which produces duplicate, confusing log entries for one
   real failure). Use `logger.exception(...)` inside an `except` block,
   which automatically records the full traceback, rather than
   hand-assembling one.
3. **Never use a bare `except:`.** It catches everything, including
   `KeyboardInterrupt` and genuine programming errors, and hides which
   failure you actually intended to handle. Catch the specific exception
   type.
4. **Library-style code shouldn't configure logging itself** (no
   `logging.basicConfig()` inside `src/huginn/`'s modules). Modules should
   create a logger and emit through it; the application entrypoint (the
   eventual CLI, KAN-31) decides how those messages actually get handled.

## 7. Testing

Covered in depth by the `superpowers:test-driven-development` skill (the
discipline: test first, watch it fail, minimal code to pass) and
`CLAUDE.md` (Huginn's specific conventions: plain pytest functions, no
mocking framework unless unavoidable, DB-free where the logic allows it).
Two general pytest practices worth naming here since neither document above
covers them:

1. **Fixtures** (`@pytest.fixture`) exist to centralize repeated setup
   across tests, not to hide what a test depends on. A fixture used across
   many tests belongs in `conftest.py`; a one-off belongs in the test file
   next to what uses it.
2. **Coverage is a diagnostic, not a target.** A coverage report shows what
   code no test touches at all, which is useful. Chasing 100% is not: it
   rewards testing trivial code and doesn't guarantee the tests that exist
   actually check the right thing. Aim to cover the behaviors that matter,
   not the number.

## 8. Security

This matters more than usual for Huginn specifically, since the pipeline
will eventually hold direct Postgres write access and fetch from external,
unauthenticated APIs.

1. **Every database query with a variable in it must use a parameterized
   query, never string formatting or concatenation.** This is the standard
   defense against SQL injection: the query structure and the data are sent
   to Postgres separately, so a hostile string in the data can never be
   interpreted as part of the query. `psycopg` (already a dependency here)
   supports this natively (`cursor.execute("... WHERE id = %s", (value,))`).
   Building a query string with an f-string or `.format()` and any
   externally-sourced value is never acceptable, no exceptions.
2. **Secrets never live in code or get committed.** Huginn already does
   this correctly: `config.py` reads `HUGINN_DATABASE_URL` from the
   environment via `.env` (which is git-ignored), never a hardcoded
   connection string.
3. **Validate input at system boundaries**, meaning anything from an
   external source (an HTTP response, a user-provided ICP filter) should be
   checked before it's trusted, even though bind variables already stop SQL
   injection specifically. Bronze's "store the raw payload verbatim" rule
   (section 4.1, `CLAUDE.md`) is compatible with this: storing raw input is
   fine, trusting its shape without checking before acting on it downstream
   is not.
4. **Least privilege for the database user** the application connects as:
   it should only be able to do what the pipeline actually needs, not hold
   superuser access. Not yet relevant since no live deployment exists, worth
   remembering once one does.

## 9. Concurrency, for I/O-bound work specifically

Relevant here because fetching HN comment trees and paginating YC's Algolia
index both mean many outbound HTTP requests, exactly the situation async I/O
is for.

**Decided, project-wide** (ADR-0003): stdlib `concurrent.futures.ThreadPoolExecutor`,
bounded (5-10 workers), not `asyncio`. The general tradeoff, for context:

1. `asyncio` (with an async-compatible HTTP client like `httpx`) suits a
   task spending most of its time waiting on network I/O with many such
   waits needed concurrently. Huginn does not use this, on purpose.
2. Threading is the simpler choice when the HTTP library in use is
   synchronous (a blocking call inside an `async def` function blocks the
   entire event loop, which defeats the point of asyncio), which is
   Huginn's situation with `requests`.
3. Never mix an unbounded number of concurrent requests with an external
   API. Every adapter caps concurrency at a small number (KAN-29 uses 8);
   that's the right default, not a detail to loosen later.

## 10. Common pitfalls worth knowing by name

A short list of mistakes that look reasonable and aren't, useful for
spotting them in a review even without deep Python background:

1. **Mutable default arguments** (`def f(items=[]):`). The empty list is
   created once, at function definition time, and shared across every call
   that doesn't pass its own. Use `None` as the default and create the list
   inside the function body instead.
2. **Catching `Exception` broadly** "to be safe." This has the same effect
   as a bare `except:` for almost every practical purpose: it hides which
   specific failure occurred and makes debugging a production incident much
   harder. Catch the narrowest exception type that's actually expected.
3. **Comparing to `None`, `True`, or `False` with `==`.** Use `is None`,
   `is True` (or usually just `if value:`); `==` can be fooled by a custom
   `__eq__` and is slower for no benefit here.
4. **Reaching for a class when a function would do.** Huginn's own code
   already favors plain functions and frozen dataclasses over classes with
   behavior, that's consistent with modern Python style, not just this
   project's taste.

## What's settled for Huginn vs. still open

Settled (see `CLAUDE.md` for the full list): src layout, `uv`, type hints
throughout, frozen dataclasses over mutable state, Protocol-based interfaces,
plain-pytest tests, mandatory TDD, no ORM (raw `psycopg` with parameterized
queries), Ruff + pyright as the linter/type-checker choice (ADR-0004, not yet
installed), `concurrent.futures.ThreadPoolExecutor` for concurrent I/O
(ADR-0003), logging required from day one (ADR-0005).

Still genuinely open: production deployment target (local only for now,
explicitly deferred until past MVP), migration tooling (hand-written DDL via
`psql`, no framework), KAN-20 (Gold Type 1/Type 2 classification, likely
already answered by existing DDL/code, needs only a confirm-and-close pass).

## Sources

1. Ruff and the consolidated Python code-quality stack. [The Complete Python Code Quality Stack in 2026](https://blog.marcosalonso.dev/the-complete-python-code-quality-stack-in-2026-ruff-mypy)
2. Type checking landscape (mypy, pyright, ty). [Modern Python Typing Tutorial 2026](https://itsourcecode.com/blogs/modern-python-typing-tutorial-2026/)
3. `src/` layout rationale. [Real Python: Project Layout](https://realpython.com/ref/best-practices/project-layout/)
4. `pyproject.toml` as the standard packaging format. [pyproject.toml: Modern Packaging Guide 2026](https://www.guvi.in/blog/python-packaging-with-pyproject-toml/)
5. SQL injection prevention via parameterized queries. [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
6. Database least-privilege and defense-in-depth. [Python Security Best Practices](https://simeononsecurity.com/articles/python-security-best-practices-protecting-code-data/)
7. pytest fixtures and coverage guidance. [Pytest Best Practices 2026](https://qaskills.sh/blog/pytest-best-practices-2026), [Pytest Coverage with pytest-cov](https://qaskills.sh/blog/pytest-coverage-pytest-cov-guide-2026)
8. Exception logging, error hiding, log-and-throw anti-pattern. [Real Python: Logging](https://realpython.com/ref/best-practices/logging/), [Error hiding, Wikipedia](https://en.wikipedia.org/wiki/Error_hiding)
9. `uv` dependency groups and lock-file workflow. [uv: The Complete Guide 2026](https://noqta.tn/en/tutorials/uv-python-package-manager-complete-guide-2026)
10. Docstring conventions. [PEP 257](https://peps.python.org/pep-0257/), [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
11. Asyncio vs. threading for I/O-bound work. [Real Python: Concurrency](https://realpython.com/ref/best-practices/concurrency/)
