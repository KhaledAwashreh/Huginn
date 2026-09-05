# Hacker News — Who's Hiring

Source of truth for Bronze-layer ingestion design. Verified live against the API on 2026-09-05 using the September 2026 thread (item `49522897`).

## Access

- **Base URL**: `https://hacker-news.firebaseio.com/v0/` (Firebase-backed, read-only, static JSON — no SDK required, plain HTTPS GET).
- **Item endpoint**: `GET /v0/item/<id>.json` — returns one item (story, comment, job, poll, or pollopt) by integer id. This is the only call needed to walk a thread: fetch the root item, then fetch each id in its `kids` array, then recurse into each comment's own `kids` for replies.
- **User endpoint**: `GET /v0/user/<username>.json` — returns a user's `submitted` array (their own item ids, most recent first). Used here to find the monthly thread (see Freshness below).
- **Auth**: none. No API key, no OAuth, no headers required. Confirmed — every call above was a bare unauthenticated GET.
- **Rate limits**: none documented/enforced by the official API (confirmed via `github.com/HackerNews/API` README, which states "There is currently no rate limit"). Community etiquette, since this is a shared Firebase-hosted service with no key-based quota to signal misuse:
  - Don't fire concurrent requests in a tight loop against `/v0/item/*` when walking a large thread (a "Who's Hiring" root can have 300+ descendants) — pace/batch requests (e.g. a small concurrency cap, tens of req/s not hundreds) or use HTTP caching.
  - `/v0/item/<id>.json` is served from Firebase's CDN and is effectively immutable once an item stops changing, so a Bronze fetch job can cache aggressively and rely on `updates` polling rather than re-scanning every item every run.
- **Unofficial complement**: the Algolia HN Search API (`https://hn.algolia.com/api/v1/search_by_date`) mirrors HN content with a real search index and is commonly used alongside the official API for discovery (see Freshness). It is not part of the official HN API and has its own (also unenforced-in-practice) usage norms.
- **Official docs**: https://github.com/HackerNews/API (README documents endpoints and item schema; this is the canonical reference).

## Response shape

An "item" is a flat JSON object; which fields are present depends on `type` and state. Confirmed fields from the README and cross-checked against live fetches:

- `id` (int, always present)
- `type`: `"story"` | `"comment"` | `"job"` | `"poll"` | `"pollopt"`
- `by`: author username (string) — **absent** on deleted items
- `time`: Unix timestamp (seconds)
- `text`: HTML-escaped string (comment/story/poll body) — **absent** on deleted items
- `title`: HTML-escaped string — only on the root story item, not on comments
- `url`: story URL — the root "Who is hiring?" item has `url: null` (it's a self/Ask-HN post, the "URL" is the discussion itself)
- `score`, `descendants`: root item only (total comment count including nested replies)
- `kids`: array of child item ids, in ranked (display) order. On the root item these are the **top-level company posts**. On a company-post comment, `kids` are replies to it (see below).
- `parent`: id of the parent item (root story id for top-level posts; the comment id for a nested reply)
- `deleted` / `dead`: booleans marking removed/flagged items. **When `deleted: true`, the item drops `by`, `text`, and `kids` entirely** — you get back only `{id, deleted, parent, time, type}`. This matters for Bronze: a previously-seen id can "go empty" on a later fetch.

### Real example — root thread item

`GET https://hacker-news.firebaseio.com/v0/item/49522897.json`

```json
{
  "id": 49522897,
  "type": "story",
  "by": "whoishiring",
  "time": 1788274877,
  "title": "Ask HN: Who is hiring? (September 2026)",
  "text": "Please state the location and include REMOTE for remote work, ...",
  "score": 247,
  "descendants": 337,
  "url": null,
  "kids": [49573833, 49524580, 49523950, 49527388, 49523712, 49525651, "... ~330 more top-level company-post ids"]
}
```

### Real example — a top-level company post (with URL)

`GET https://hacker-news.firebaseio.com/v0/item/49573833.json`

```json
{
  "by": "srikanthkasa",
  "id": 49573833,
  "parent": 49522897,
  "time": 1788591349,
  "type": "comment",
  "text": "Supero | Cloud &#x2F; Platform Engineer | REMOTE (SF Bay Area, CA, US · Bengaluru, KA, India) | Full-time | <a href=\"https:&#x2F;&#x2F;www.supero.dev&#x2F;careers&#x2F;cloud-platform-engineer&#x2F;\" rel=\"nofollow\">https:&#x2F;&#x2F;www.supero.dev&#x2F;careers&#x2F;cloud-platform-engineer&#x2F;</a><p>We generate full-stack apps and deploy them ... <p>4+ years production infra, Kubernetes past the tutorial, AWS and&#x2F;or GCP at depth. ..."
}
```

Note the escaping: `/` is written `&#x2F;`, links are inline `<a href="...">`, paragraph breaks are bare `<p>` (not `<p>...</p>`) — this is HN's normal comment-rendering HTML, not a hiring-thread-specific format.

### Real example — a top-level company post with no URL at all

`GET https://hacker-news.firebaseio.com/v0/item/49533854.json` (CNIO, a Spanish cancer research institute) ends with:

```
"...Bonus: Ceph, Kubernetes, GPU stacks, a bioinformatics background<p>Spanish not required<p>If interested: tdidomenico-at-cnio-dot-es."
```

No `<a href>`, no bare URL string, no domain — the entire "how to apply" is an obfuscated email address. This is a real, current-thread example, not a hypothetical.

### Real example — a deleted item

`GET https://hacker-news.firebaseio.com/v0/item/49524098.json`

```json
{
  "deleted": true,
  "id": 49524098,
  "parent": 49522897,
  "time": 1788279499,
  "type": "comment"
}
```

`by`, `text`, `kids` are simply absent — not null, not empty string, gone.

### Real example — a nested reply (applicant Q&A, not a company post)

`GET https://hacker-news.firebaseio.com/v0/item/49532514.json`, a reply to the Wikimedia post (`parent: 49524580`, itself a top-level child of the root):

```json
{
  "by": "Washuu",
  "id": 49532514,
  "parent": 49524580,
  "time": 1788330899,
  "type": "comment",
  "text": "Working for Wikimedia would make me actually consider moving back to the USA for the opportunity. (I'm in Japan for reference.) I previously contributed to Mediawiki..."
}
```

`parent` here points to another **comment**, not to the root story — this is the structural signal that distinguishes a nested reply from a top-level company post (see Open questions below).

## Freshness / cadence

- One new root "Ask HN: Who is hiring? (Month Year)" item is posted monthly by the `whoishiring` bot account, alongside a companion "Who wants to be hired?" post at the same timestamp. Per the account's own `about` field (`GET /v0/user/whoishiring.json`): *"This account automatically submits a 'Who is hiring?' post at 11 AM Eastern time on the first weekday of every month."*
- Confirmed live: `whoishiring.submitted` returns ids in descending order, most recent first, e.g. `[49522897 (Sep 2026 hiring), 49522896 (Sep 2026 wants-to-be-hired), 49156683 (Aug 2026 hiring), 49156682 (Aug 2026 wants-to-be-hired), ...]` — the two threads for a given month are consecutive ids, hiring first.
- **Reliable discovery for a scheduled job**, in order of robustness:
  1. `GET /v0/user/whoishiring.json`, take `submitted[0]`, fetch that item, and check `title` matches `/^Ask HN: Who is hiring\? \(/` (skip it if it's actually the "wants to be hired" companion — filter by title, don't assume position).
  2. As a cross-check / alternative, query Algolia: `GET https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=5` and take the newest hit whose `title` starts with "Ask HN: Who is hiring?". This avoids depending on `submitted` array ordering/size and gives `created_at` directly.
  3. Do **not** hardcode a "runs on the 1st" assumption — the account posts on the first *weekday*, so the id/date shifts around weekends/holidays. Poll (e.g. daily) rather than cron-firing on a fixed day-of-month.
- Once the root id is known, re-fetching the same job periodically through the month is worth doing: `descendants`/`kids` grow for days after posting as more companies reply, and `/v0/updates.json` lists recently changed item ids if you want to avoid re-walking the whole tree to catch new comments.

## Signal mapping (proposed Bronze fields)

Bronze should store the raw item verbatim (all fields above, including `text` un-parsed) plus a couple of derived-but-still-"raw" fields that are cheap and lossless to extract at ingest time, deferring anything lossy to Silver. Based on the 9 real top-level posts sampled above:

| Signal | Reliably extractable at Bronze? | Notes |
|---|---|---|
| Raw post text (`text`) | Yes, always | Store verbatim HTML-escaped string. This is the only field guaranteed to carry everything. |
| Company name | Partially | Almost always the first token(s) before the first `\|` or first `<p>`, but there is **no enforced template** — some posts lead with role or location instead. Cheap regex/heuristic can get a plausible candidate; guaranteed-correct extraction needs Silver-level parsing/NER. |
| URL / domain | **Sometimes** — in this sample, 8 of 9 top-level posts (~89%) had at least one `<a href>` or bare URL; 1 of 9 (CNIO) had none, only an obfuscated email. Treat "has a URL" as a boolean Bronze field, not an assumption. | Even when present, a post can contain multiple URLs (careers-page link, company homepage, YouTube culture video, ATS deep link like `job-boards.greenhouse.io/...`) — Bronze should capture **all** `href`s found, not just the first, and leave "which one is the company's canonical domain" to Silver/entity resolution. This is exactly the ambiguity that affects entity resolution design elsewhere in the project — do not assume 1 post → 1 domain. |
| Location | Loosely | Free text near the top (e.g. `REMOTE (US)`, `ONSITE (CH)`, `Berlin, Germany`, `HYBRID`) but format varies post to post — sometimes a country code, sometimes a city, sometimes both, sometimes absent. Extractable as a raw substring only; structured geocoding is a Silver task. |
| Remote-friendly | Loosely | Keywords `REMOTE`, `ONSITE`, `HYBRID`, `Remote (Canada)`, `REMOTE (US)` etc. appear near the top of most posts but capitalization/placement is inconsistent (some posts skip it entirely and only mention it inline). Bronze can store a raw keyword-match flag; don't treat absence as "not remote." |
| Role keywords | Yes, as raw text | Job titles are free text (e.g. "Cloud / Platform Engineer", "Senior Solution Engineer (Observability & Linux)"); a bulleted list of multiple open roles is common in a single post (see PlantingSpace, Quobyte, VictoriaMetrics examples above) — one post can map to many roles. Bronze should not force 1-role-per-post. |
| Funding/stage mentions | Rare, freeform | Occasionally explicit ("closed our Series A last year", "2nd time founders") but most posts say nothing about funding/stage. Not reliably present; capture only if doing a keyword scan, and expect it to miss most companies that just don't mention it (not necessarily unfunded). |
| Design/product hiring mentions | Yes, as keyword matches | Role titles like "Lead Product Manager", "Product Engineer", "Product Marketing Manager" are plain substrings of the role line and/or bullet list; straightforward to flag at Bronze with a keyword scan, same caveat as role keywords above (freeform, no fixed field). |
| Company/user identity | Yes, always | `by` (the HN username who posted) is always present on non-deleted items and is a reliable join key even though it is a personal account, not a verified company identity — useful for Bronze provenance, not for entity resolution by itself. |

## Open questions / risks

- **No fixed template**: posts are 100% freeform prose with a loosely conventional `Company | Role | Location | Type | URL` first line — but every field in that convention is optional and ordering varies (see PSI example: institute name, role, ONSITE, full-time, duration, then a bare `www.psi.ch` with no `http://` scheme and no `<a>` tag — a bronze URL-extraction regex anchored on `<a href>` alone would miss this). Any Bronze-level parsing beyond "store raw + flag presence of link/keyword" is guessing, not extracting.
- **Template drift over time**: because there's no schema enforcement, conventions can shift month to month as HN culture/norms shift (e.g. more/less use of `|` delimiters, AI-related caveats becoming common — several 2026 posts here mention AI-native/AI-assisted hiring, which wasn't a category a few years ago). A Bronze design that hardcodes delimiter assumptions will silently degrade; keep parsing logic in Silver and versioned/revisitable.
- **Non-company noise**: the root thread's `kids` are supposed to be exclusively company posts per the pinned instructions ("must personally be part of the hiring company"), but nothing in the API enforces this — moderators can `dead`-flag off-topic top-level comments, but Bronze will still see them via `kids` unless it also checks `dead`. Filter/flag `dead: true` items rather than assuming all `kids` are legitimate company posts.
- **Deleted items**: as shown above, a `deleted: true` item loses `by`/`text`/`kids` outright. A Bronze ingest job that snapshots the thread early and re-fetches later must handle previously-captured content "disappearing" from the source — decide whether Bronze treats this as a tombstone (keep prior capture, mark deleted_at) or as data loss to accept.
- **Top-level vs nested replies**: only items whose `parent` equals the root thread id are company posts; anything whose `parent` is itself a comment id is a nested reply (applicant questions, follow-up clarifications, unrelated banter) and should **not** be treated as its own signal source. This is a simple structural check (`parent == root_id`) but requires walking `kids` recursively and checking `parent` at each level rather than assuming "everything under the root, at any depth, is a job post." The Washuu reply example above is representative of this noise (personal commentary, not a listing).
- **Multiple URLs per post, ambiguous canonical domain**: several sampled posts contain 2+ links (apply link + intern-role link + YouTube + company homepage). Bronze should capture the full set; deciding which one is "the company's domain" for entity resolution is explicitly out of scope for Bronze and belongs to Silver/Gold.
- **One post, multiple roles**: posts frequently list several open roles (sometimes across multiple locations/remote policies) in a single comment. If Bronze/Silver design assumes a 1:1 post-to-role mapping, that assumption will be wrong for a meaningful share of posts — plan for one company post to yield zero, one, or many role-level Silver records.
- **Rank/order in `kids` is not chronological in a simple sense**: HN's ranking algorithm affects `kids` order (it's described as "ranked" order, not strictly insertion order), so don't rely on `kids` array order as a reliable proxy for "most recently posted" — use each item's own `time` field for that.
