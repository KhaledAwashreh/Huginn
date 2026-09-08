# Orchestration upgrade path off cron: Prefect OSS vs. GitHub Actions schedule:

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-9

## Why this came up

Cron plus a `job_runs` table is confirmed as the correct MVP default for
2-10 scheduled pulls a day (ADR territory, see `db/schema/ops.sql`), but two
concrete upgrade paths were named for later, not evaluated in depth yet.

## What this is about

Dagster was explicitly ruled out: Dagster+ got more expensive for solo/
starter tiers as of May 2026 (included credits removed, moved to
per-asset-materialization billing). Two named alternatives for whenever bare
cron stops being enough:

1. **Prefect OSS**, self-hosted, free, wraps plain Python functions/decorators
   (no DAG-definition framework required), adds retries-with-backoff,
   run-history UI, and alerting.
2. **GitHub Actions `schedule:`**, zero infrastructure, free (2,000 minutes a
   month private, unlimited public), workflow YAML doubles as deployment.
   Caveats: UTC-only, best-effort (not exact) timing, auto-disables after 60
   days of repository inactivity.

## Closest Java/C# equivalent

Prefect's "wrap a plain function with scheduling/retries" model resembles
Quartz Scheduler in Java or Hangfire in .NET. GitHub Actions' `schedule:`
has no close analogue, it's a CI-platform feature, not a language pattern.

## Key concepts to learn

1. Enough of Prefect's actual API to judge how much it would change existing
   adapter/service code versus just wrapping it.
2. GitHub Actions' `schedule:` limits in practice: the UTC-only and
   best-effort timing caveats, and what "auto-disables after 60 days" means
   for a project with irregular commit activity.
3. The actual trigger point for migrating off bare cron, not just "cron
   feels primitive," a concrete signal worth watching for.

## Resources

1. `architecture-notes/data-pipeline-standards.md`, "Orchestration at solo
   scale" section.
2. Prefect OSS docs; GitHub Actions `schedule:` documentation.

## Notes

