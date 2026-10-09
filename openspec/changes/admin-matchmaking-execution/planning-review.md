# MVP planning checkpoint

Date: 2026-10-09. User approved the brainstorm, then explicitly requested plans first. This checkpoint concerns planning artifacts only; no implementation task is complete.

Revised proposal/design/spec/tasks in `pipeline-control-and-history` and `admin-pipeline-console`. Scaffolded `admin-matchmaking-execution` and `user-matches-view` through `openspec new change`, then created all four spec-driven artifacts in dependency order using CLI instructions.

Implementation source was inspected read-only in `.worktrees/user-configuration-workspace`, whose HEAD is `7fc076a646af23d7502f9754f62dfdcb97ed04c4` and whose reviewed configuration implementation is currently uncommitted. Planning copies remain in the primary checkout. Use the actual merged successors or reviewed implementation source when later applying; these documents do not create or merge that base.

## Dependencies and MVP boundaries

1. `pipeline-control-and-history`: authoritative user/admin roles, additive queue/history/guard, existing full collection execution, and transaction-linked Gold company results.
2. `admin-pipeline-console`: Data collection/Pull data browser workflow, stage/source progress, history, and paginated current fields of companies written by the selected run.
3. `admin-matchmaking-execution`: separate admin workflow invoking the existing creation-only service for one user or a fixed set of active users with active strategies. It depends on the pipeline backend; its UI is independent of the collection UI.
4. `user-matches-view`: read-only own match list/detail/signals, depending on configuration and durable matching result tables for truthful overview context.

Collection and matching have separate triggers and queues but share exclusive execution admission. Progress means finished stages or settled users, not estimated duration or company scans. Existing Match identity/status/notes and matching criteria are preserved. Company/signals are current context, not historical why-matched evidence. The proposed editable signal-window default is30days, with7/30/90/custom presets. No automatic matching after collection, scheduler, ranking/scoring, digest, CRM, user matching trigger, or status/notes editing is included.

## Review and verification

Narrow planning groups used Luna; parent integrated the shared contracts and inspected delegated artifacts. Fresh-context Sol high independently read all four change sets, relevant current source, and reran strict validation/status. Initial actionable findings were corrected in the affected planning artifacts:

- Preserve the actual `CompanyWriter.write_all()` batch transaction and existing repository cursor for Gold attribution; include the upsert return/port and materialization context injection inventory.
- Ensure invocation/job attribution consistency with a composite reference and allowlist company-result fields.
- Keep base ops bootstrap before Gold/operational; apply FK-dependent control migrations afterward on fresh and existing installations.
- Separate short trigger admission lock namespaces from the long shared session execution lock.
- Provide proven-stopped standalone matcher execution reconciliation as well as managed-run reconciliation.
- Distinguish filtered/out-of-range empty match pages from owner-wide empty results.
- Keep read projections in application/read_models and query Protocols, split boundary models, and complete matching query/page/recovery inventories.

Final fresh-context Sol high review is clear: no remaining actionable planning findings. The reviewer independently reran all four strict validations and statuses after the fixes; each change passes and has4/4 planning artifacts complete. Parent independently reran the same gates and checked that every requirement has scenarios, each required artifact exists, inventory paths are unique, and all implementation tasks remain unchecked (pipeline22, collection UI12, admin matchmaking17, user Matches10).

Runtime services, real PostgreSQL data, primary ops edits, unrelated planning/worktrees, dependency installations, and existing implementation checkboxes have not been changed by plan preparation. No application tests or browser gates were executed for document-only changes; future implementation tasks explicitly retain those required gates. No Jira updates, commits, pushes, or PRs.
