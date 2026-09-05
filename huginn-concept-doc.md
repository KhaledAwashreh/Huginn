# Huginn — Client Discovery Tool for Independent Service Providers

**Status:** Concept · v1.3
**Last updated:** August 2026
**Living document.** Sections marked 🔴 are unresolved. Working name "Huginn" is low-stakes, parked in §13.

---

## 1. Problem Statement

Finding leads is one of the hardest parts of running a services business — often the hurdle that stops people from going independent at all. No sales team means prospecting competes directly with billable work.

Startups make it worse. They lack the org charts, headcount plans, and formal recruiting processes that make bigger companies legible from the outside. But that same scrappiness is the opportunity: fast, informal, no-procurement-cycle startups are exactly what solo providers are built to serve. The gap isn't fit — it's **visibility**. The signal exists (funding, hiring, program milestones); it's just scattered and easy to miss on top of client work.

## 2. Vision

Monday morning, an email is already waiting: a handful of companies that could be meaningful leads, right now. Not a feed to monitor — a short shortlist, already checked against criteria set by the user themselves.

Each entry gives enough to know quickly if it's worth a message: who they are, why they surfaced, and a starting line for outreach. Reaching out becomes a Monday habit instead of a task that keeps getting pushed to later.

Over time the list gets better — it learns what a "yes" and "no" actually look like for this person. **The hardest part of running a services business — finding who needs you — happens in the background, and the result is waiting every Monday.**

## 3. Solution

User defines an ICP in plain language → system collects public signal continuously → scores every prospect against that ICP → delivers a ranked shortlist weekly.

**Startup-focused is the pool, not the audience.** Startups make v1 tractable — a legible, well-documented ecosystem. But the real need ("I'm independent, I need clients, I don't have time to monitor a dozen sources") isn't startup-specific. 🔴 Same engine could point at a different pool later (e.g. skilled trades) — not building that now, just not closing the door.

**Core insight:** collection is shared infrastructure, matching is personal. One pool can serve many ICPs without re-scraping per user — what makes this plausible as a product later, even with an audience of one today.

## 4. Who This Is For

| Tier | Who | Note |
|---|---|---|
| **Now (v1)** | Fractional 0→1 product/design consultant | ICP detail in `craig-consulting-context.md` |
| **Later** | Independent service providers broadly — consultants, solo agencies, freelance specialists, recruiters, fractional CFOs, dev shops | Same startup pool, different ICP per user. 🔴 Not designed for yet, just not blocked |
| **Parked** | Same engine, different pool (e.g. skilled-trades client discovery) | Out of scope until the startup version validates |

## 5. What It Delivers

| Delivers | Does not deliver |
|---|---|
| Weekly digest, handful of ranked companies | Job postings as the end product — they're an input signal, not the output |
| Per company: name, site, LinkedIn *search link* (not scraped — §8), short description, plain-language match reasoning, drafted outreach opener | Scraped LinkedIn profile data (ToS risk — §8) |
| | Outreach automation, sequencing, or CRM — the opener is a draft to edit and send yourself |
| | Real-time alerts — weekly batch by design |

**What a digest entry looks like:**

```
┌────────────────────────────────────────────────┐
│  Acme AI                                        │
│  acme.ai  ·  LinkedIn search →                  │
│                                                  │
│  What they do                                   │
│  AI-powered supply-chain forecasting for         │
│  mid-market retailers                            │
│                                                  │
│  Why you're seeing this                          │
│  Raised $4M seed 3 days ago · no design hire     │
│  visible in their HN "Who's Hiring" post          │
│                                                  │
│  Try this opener                                 │
│  "Saw the seed round — congrats. Curious how     │
│  you're thinking about onboarding UX as the      │
│  sales team scales..."                           │
└────────────────────────────────────────────────┘
```

## 6. How It Works

```
[Sources] → [Ingestion] → [Shared Pool] → [Scoring per ICP] → [Weekly Digest]
                                                  ↑
                                    [Feedback: sent / seen / dismissed]
```

1. **ICP profile** — plain-language input, parsed into structured filters (stage, sector, team signal, funding recency, program pedigree), editable and re-parsed as it evolves
2. **Ingestion** — scheduled pulls per source, normalized to: `company, signal_type, stage, sector, source, date, url(s)`
3. **Shared pool** — deduplicated, accumulating, source-agnostic
4. **Scoring** — weighted match on stage, sector, team-composition signal, recency, source quality
5. **Delivery** — top N unseen matches, ranked, with description + match reasoning + drafted opener
6. **Feedback loop** — 👍/👎 per lead adjusts that user's scoring weights over time

🔴 **Team-composition signal is unresolved.** "No designer on staff" is too specific to reliably infer from public data. Needs a coarser proxy — team size, funding stage, visible hiring history — tested once there's real HN/YC data to check against.

## 7. Candidate Sources

| Source                                                                                                   | Signal                 | Ingestion path 🔴                            |
| -------------------------------------------------------------------------------------------------------- | ---------------------- | -------------------------------------------- |
| HN "Who's Hiring"                                                                                        | Hiring, monthly        | Official API — easiest, most reliable        |
| YC directory                                                                                             | Company, batch, sector | Public; check ToS before scheduled access    |
| VC portfolio boards (Sequoia, a16z, Index, Greylock)                                                     | Hiring, funded         | Often Getro-based — look for a JSON endpoint |
| Ramp vendor reports                                                                                      | Growth (spend)         | Likely manual/periodic; may be paid-gated    |
| Harmonic Hot 25                                                                                          | Growth, ranked         | Quarterly — manual or email-parse            |
| Founders You Should Know                                                                                 | Curated growth         | Newsletter — email-parse via Gmail API       |
| Next Play                                                                                                | Under-the-radar hiring | Newsletter — email-parse                     |
| Early Days Substack                                                                                      | Deep-dive signal       | Newsletter — email-parse or RSS              |
| a16z Build                                                                                               | Curated hiring         | Newsletter — email-parse                     |
| [https://cordis.europa.eu/about/dataextractions-api](https://cordis.europa.eu/about/dataextractions-api) |                        |                                              |
| [https://api.opencorporates.com/](https://api.opencorporates.com/)                                       |                        |                                              |

Two ingestion strategies: **live/scrape-able** (HN, YC, VC boards) vs. **periodic newsletters** (the rest) — likely parsed from a dedicated subscription inbox. Validate each individually.

## 8. Constraints & Risks 🔴

- **LinkedIn ToS** — no scraping/storing profile data (see hiQ v. LinkedIn). Search-URL links only.
- **Source ToS** — check robots.txt/terms for YC and VC boards before scheduled access.
- **Newsletter content** — personal-use parsing ≠ redistribution rights; revisit if multi-user.
- **Data gating** — Ramp/Harmonic may only expose the published report free; don't assume an API exists.
- **Deliverability** — sending to self via Gmail API sidesteps spam concerns for now; matters more if multi-user.

## 9. Open Questions

| Question                                                      | Blocking? |
| ------------------------------------------------------------- | --------- |
| Weekly vs. daily cadence? (leaning weekly)                    | No        |
| Which 2 sources first? (lean: HN + YC — cleanest paths)       | **Yes**   |
| What's actually inferable as team-composition signal?         | No        |
| Scoring weights user-editable, or feedback-only?              | No        |
| Lightweight UI, or stay email + config/sheet?                 | No        |
| ~~Timeline?~~ Resolved — next few weeks, alongside other work | Resolved  |

## 10. Phased Approach

| Phase | Scope | Goal |
|---|---|---|
| **0 — Personal PoC** *(now, next few weeks)* | Solo · HN + YC · simple scoring (stage/sector/recency) · drafted openers attempted, fallback to skip if quality is weak · no feedback loop yet | Does this surface leads I wouldn't find manually? |
| **1 — Sharpen** | Add VC boards + newsletters one at a time · add 👍/👎 feedback loop | Precision over recall |
| **2 — Generalize** | Test with 1–2 other consultants, different ICPs · validate ICP-parsing beyond my own phrasing · still no billing/auth | Does the matching quality hold for someone else? |
| **3 — Product** 🔴 | Not scoped | Revisit after Phase 2 |

## 11. Architecture Note

Model as multi-user from day one, even with one user:

```
   users            companies          matches
 (icp_profile) ──▶ (shared pool) ◀── (user × company,
                                       score, status)
```

Keeps ingestion/scoring decoupled from "who's using it" — Phase 2 becomes additive, not a rebuild.

## 12. Success Signal for Phase 0

No formal metrics yet. Honest test: **after 3–4 digests, has at least one company been contacted that wouldn't have been found through the existing pipeline?** If yes, keep investing. If leads are consistently off-ICP or redundant, rework scoring before adding sources.

## 13. Naming (low priority)

Working name: **Huginn** — one of Odin's ravens, flies out daily, reports back. Placeholder, not a real decision yet.

Alternates: **Reynard** (trickster fox — sharper voice), **Puck** (mischievous messenger — lighter voice). Lower priority: Muninn, Garuda, Ratatoskr, Ariadne, Percival, Anansi, Bloodhound.

---

## Changelog
- **v0.1** — Initial concept doc.
- **v0.2** — Named the working concept "Huginn."
- **v0.3** — Reframed from "startup lead tool" to "client discovery tool for independent service providers."
- **v0.4** — Resolved build team + timeline. Softened "no designer on staff" to an open team-composition question.
- **v0.5** — Deepened Problem Statement / Vision with the underlying "why."
- **v0.6** — Rewrote Vision as an experience, not a tool description.
- **v0.7** — Split Vision (§2) from Solution (§3); renumbered sections.
- **v0.8** — Toned down Vision — less flowery.
- **v0.9** — Wording tweak: "meaningful leads."
- **v1.0** — Added company description, match reasoning, and drafted outreach opener to what each digest entry delivers.
- **v1.1** — Trimmed prose throughout; added ASCII diagrams (pipeline, sample digest entry, table relationships) and converted several sections to tables for scannability.
- **v1.2** — Removed personal names throughout (owner, collaborators) in favor of generic references.
- **v1.3** — Removed owner/collaborator framing entirely — dropped the Owner metadata line, the "Building Phase 0 with" line, and the Owner column from Open Questions.
