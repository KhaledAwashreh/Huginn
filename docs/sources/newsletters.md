# Newsletter Sources (Founders You Should Know, Next Play, Early Days, a16z Build)

> Research date: 2026-09-05. All four are confirmed Substack publications with working public RSS feeds — the prior working assumption that these would require Gmail-inbox email-parsing does **not** hold. RSS is the simpler and more robust ingestion path for Bronze.

## Access

### Founders You Should Know
- **Platform:** Substack, served on a custom domain (`newsletter.foundersysk.com`) rather than `*.substack.com`.
- **RSS feed:** `https://newsletter.foundersysk.com/feed` — confirmed live, valid RSS 2.0. Custom-domain Substack publications keep the standard `/feed` path.
- **Publisher:** Independent media outlet ("DK" / Founders You Should Know team), paired with monthly in-person founder showcases in San Francisco.
- **Email-parsing fallback:** Not needed, but if ever required, note the newsletter's content is built around named "Showcase Primer" posts profiling 2-4 founders/companies per issue — fairly parseable structure even as HTML email.

### Next Play
- **Platform:** Substack, on the default subdomain `nextplayso.substack.com`.
- **RSS feed:** `https://nextplayso.substack.com/feed` — confirmed live, valid RSS 2.0, feed title "next play".
- **Publisher:** Ben Lang / next play team (`hi@nextplay.so`); also runs a separate curated job board and paid community outside the newsletter itself.
- **Email-parsing fallback:** Not needed.

### Early Days
- **Platform:** Substack, on the default subdomain `earlydaysbymerlin.substack.com` (this is the correct "Early Days" for our purposes — run by Cam Ricketts and Brie Wolfson, covering "Silicon Valley companies, people, jobs, and ideas"; note there is at least one other unrelated Substack also titled "The Early Days" by Evis Drenova (`evis.substack.com`), which is not the one referenced here — worth double-checking against the subscription inbox sender address before wiring up ingestion).
- **RSS feed:** `https://earlydaysbymerlin.substack.com/feed` — confirmed live, valid RSS 2.0, feed title "early days".
- **Publisher:** Cam Ricketts and Brie Wolfson.
- **Email-parsing fallback:** Not needed.

### a16z Build
- **Platform:** Substack. Important finding: the publication has been **renamed/moved**. `https://a16zbuild.substack.com` now returns a 301 redirect to `https://a16zjobs.substack.com` (confirmed on both `/feed` and `/about`). The newsletter now brands itself "a16z Jobs."
- **RSS feed:** `https://a16zjobs.substack.com/feed` — confirmed live, valid RSS 2.0, feed title "a16z Jobs", description "New jobs every day."
- **Publisher:** Katie Kirsch and the a16z New Media team. Content is centered on a16z portfolio companies and their hiring/fundraising activity, with occasional non-a16z-backed roles included.
- **Email-parsing fallback:** Not needed. If the old `a16zbuild.substack.com/feed` URL is hardcoded anywhere, it will keep working via the redirect, but ingestion config should point at the new `a16zjobs.substack.com` domain directly to avoid depending on the redirect long-term.

## Response shape

All four feeds are standard Substack RSS 2.0: `<channel>` with `<item>` entries carrying `<title>`, `<link>`, `<pubDate>`, `<guid>`, `<description>` (an HTML-escaped excerpt/summary), and typically `<content:encoded>` with the fuller post body as embedded HTML (images, formatting, etc. inline — not plain text). Full post content beyond the feed's excerpt/description may require following `<link>` to the web version, since Substack feeds sometimes truncate long posts or paywall parts of premium content. None of the four require authentication to read their free-tier feed content based on what was checked; paid-tier/premium sections (if any) would not appear in the public feed.

## Freshness / cadence

- **a16z Jobs (formerly a16z Build):** Near-daily — observed 3 consecutive daily posts (Sep 2-4, 2026).
- **Next Play:** Very frequent, close to daily on weekdays — observed posts on Aug 30, Sep 1, 2, 3 (2026).
- **Founders You Should Know:** Roughly weekly to biweekly, timed around showcase events — observed posts Aug 19, Aug 25, Sep 1, Sep 3 (2026).
- **Early Days:** Irregular, lower frequency — several posts in mid-to-late July 2026, then a gap with the most recent item dated Aug 3, 2026 (over a month before this research date). Cadence should be treated as unreliable; worth periodic health-checking rather than assuming a fixed schedule.

Practical implication: a polling ingestion job should check feeds at least daily to avoid missing items from the higher-frequency sources (a16z Jobs, Next Play), while Early Days may go quiet for weeks at a time.

## Signal mapping (proposed Bronze fields)

General shape: `{company, signal_type, source, date, url}` plus a raw payload/body field for later re-parsing.

- **Founders You Should Know:** Issues are usually "Showcase Primer" posts each profiling 2-4 named companies/founders with a blurb (sector, what they do, sometimes funding/hiring context) ahead of an event. This is close to a natural one-issue-to-several-records mapping: one Bronze record per company blurb per issue, `signal_type` likely "founder/company spotlight". Some issues are pure event-announcement posts with a company list only (lower signal density, still parseable).
- **Next Play:** Mixed format — many issues are explicit curated lists ("35 tiny teams now hiring", market maps) that map cleanly to one record per company/role mentioned; other issues are single-company deep dives ("Should you join: Decimal") that map to one record with more narrative content. `signal_type` should distinguish "hiring list item" vs "featured deep dive".
- **Early Days:** Least structured of the four. Content is often essay/culture commentary ("SF's cyclical optimism," "jock, nerd, prep, goth") rather than a clean company-by-company list, though it periodically runs a structured "Jobs & Talent Board" issue with named companies/candidates. Expect this source to require more manual/LLM-assisted extraction per issue rather than a mechanical list-to-record mapping — many issues may yield zero or one weak signal record, occasional issues yield several.
- **a16z Jobs (formerly a16z Build):** Most structured of the four for signal extraction — issues are titled around specific named founders/companies hiring ("The founders of Robinhood, Rivian, and Casper are all hiring...", "Bridgit Mendler, Alex Atallah... are all hiring right now") and the body enumerates open roles per company. Maps well to one record per company mentioned per issue, `signal_type` = "hiring" (occasionally "fundraising" or "talent move" per the About page's mention of periodic takeover editions on founding stories/culture).

## Open questions / risks

- **Substack feed completeness:** Need to verify in a later phase whether Substack RSS feeds include the *entire* post body (via `content:encoded`) for these specific publications, or only a truncated excerpt — this determines whether the feed alone is sufficient for Bronze or whether a secondary fetch of each `<link>` is still required.
- **Substack feed item limits:** Substack RSS feeds typically cap at a fixed number of recent items (commonly ~20-30) with no pagination — a backfill of older history is not available via RSS and would need the publication's public archive pages or email export instead.
- **a16z Build → a16z Jobs rename:** Confirmed as a domain/brand change via 301 redirect, not a shutdown. Any config or code should target `a16zjobs.substack.com` going forward; if a subscription or bookmark still points at `a16zbuild.substack.com`, it will keep resolving via redirect but this should not be relied on indefinitely (Substack could stop honoring it, or the account could churn again).
- **Early Days name collision:** At least one other Substack publication is also titled "Early Days" / "The Early Days" (by Evis Drenova, `evis.substack.com`) with a different, unrelated focus. Ingestion config must key off the exact domain (`earlydaysbymerlin.substack.com`), not the display title, to avoid accidentally pulling the wrong feed.
- **Early Days cadence risk:** The apparent >1 month gap since the last observed post (as of this research date) suggests the newsletter may be irregular, paused, or the fetch simply hit a caching/visibility limit — worth re-checking closer to actual implementation time rather than assuming the cadence data above is still current.
- **Paid/premium content:** None of the four appeared to gate content behind a paywall in what was checked, but this should be reconfirmed at implementation time — Substack allows partial free/partial paid posts, and a paid section would not appear in the public RSS feed.
- **HTML/image-heavy bodies:** Even via RSS, post bodies are HTML (not plain text) and likely include embedded images (e.g., company logos, screenshots) — Bronze storage should keep the raw HTML payload as-is and defer cleanup/plain-text extraction to a later normalization stage, consistent with the "close to source" Bronze principle.
- **Not part of MVP:** This entire source category remains a later-phase addition per current scope; this document is a feasibility reference only, not a build spec.
