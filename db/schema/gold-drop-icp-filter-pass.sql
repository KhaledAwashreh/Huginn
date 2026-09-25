-- gold.company and gold.company_history lose icp_filter_pass.
--
-- Why (ADR-0008): an ICP is one user's description of who they want to sell
-- to, so the filter verdict is per-user, while gold.company is a shared
-- dimension that the ELT pipeline writes without knowing anything about
-- users. A single un-namespaced boolean cannot hold that verdict once a second
-- user exists. It could only mean "passes *someone's* ICP", which would put
-- companies into a user's digest that fail that user's own filter, or "passes
-- *the* ICP", which is a singleton pretending to be shared state and would need
-- a migration rather than the additive change architecture document section 2
-- promises.
--
-- The column was also never populated: NOT NULL DEFAULT false on all 4,423 live
-- rows, with no writer anywhere in the tree, so this is a pure deletion with no
-- behavioural change. Where a per-user verdict belongs is left to the matching
-- step (Jira KAN-18), which owns users and already has the right grain in
-- operational.match, keyed (user_id, company_id).
--
-- Dropping it from company_history as well as company: leaving a NOT NULL
-- column with no writer on the history table would make every future history
-- insert supply a value for a verdict the Gold layer no longer holds. ADR-0002
-- describes "a Type 2 tracked field" generically and never enumerates the
-- three, so its text is unaffected; TYPE_2_TRACKED_FIELDS in
-- src/huginn/elt/gold/dimensional.py is now business_sector and
-- team_composition_signal.
--
-- Idempotent.

ALTER TABLE gold.company_history
    DROP COLUMN IF EXISTS icp_filter_pass;

ALTER TABLE gold.company
    DROP COLUMN IF EXISTS icp_filter_pass;
