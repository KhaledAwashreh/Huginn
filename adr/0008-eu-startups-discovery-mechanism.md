# 0008: EU-Startups discovery walks the sitemap only, not category pages

Status: Accepted
Date: 2026-09-17
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting, autonomous overnight run per explicit authorization, KAN-64)

## Context and Problem Statement

KAN-64's own ticket text asks for two things that read as both-required but
are not: "discovers new startup listings by walking the site's per-country
directory pages, using the sitemap `lastmod` as an incremental watermark,"
plus a separate scope item to walk
`/directory/wpbdp_category/<country-slug>-startups/page/N/`. The research
this ticket cites (`docs/sources/eu-startups.md`) treats these as
alternatives ("paginate `/directory/` by country **or** use the sitemap
listing-URL walk"), not a combined pipeline, and the ticket itself never
resolved which one is authoritative. Left unresolved, an implementer would
build both discovery paths, doing meaningfully more work than either one
alone for no benefit: the sitemap enumerates every listing URL directly
with a `lastmod` per entry (165 files today), while category-page pagination
requires walking hundreds of pages per country (Germany alone is 4563
listings at 11/page) and carries no per-listing timestamp at all, so it
cannot serve as the incremental watermark the ticket itself asks for.

A second, related gap: category-listing cards (confirmed live,
`docs/sources/eu-startups.md`) show only Category, Based in, Tags, Founded,
missing Business Description and Website, both of which the ticket's own
acceptance criteria list as always-present fields. Only the individual
`/directory/<slug>/` detail page carries the full field set. This is true
regardless of which discovery mechanism finds the URL in the first place.

## Decision Drivers

1. The sitemap already gives everything a watermark needs: a flat list of
   every listing URL plus a `lastmod` timestamp per entry, discoverable at
   runtime from `sitemap_index.xml` (no hardcoded file count). Category
   pages give neither a flat URL list at low request cost nor any
   per-listing timestamp.
2. Fewer total requests: walking 165 sitemap files finds every listing URL
   that exists today. Walking category pages for the same coverage is
   hundreds of page fetches per country, for URL discovery alone, before a
   single detail page is even fetched.
3. Either mechanism still needs one fetch per listing's detail page to get
   Business Description and Website (Decision Driver above), so category-
   page pagination buys no reduction in that unavoidable cost, it only adds
   a second, more expensive way to discover the same URLs the sitemap
   already gives for less.

## Considered Options

1. Sitemap-only discovery: walk `sitemap_index.xml`'s
   `wpbdp_listing-sitemap*.xml` files for the URL+`lastmod` list, fetch each
   new/updated listing's detail page for the full field set. (chosen)
2. Category-page-only discovery: walk `/directory/wpbdp_category/.../page/N/`
   per country, no sitemap use at all.
3. Both, as the ticket's literal text could be read: category pages for
   discovery, sitemap for the watermark layered on top.

## Decision Outcome

Chosen option: 1, sitemap-only. It is strictly cheaper than option 2 for
the same coverage, and option 3 does no useful work beyond option 1 (the
sitemap already supplies both the URL list and the watermark option 3
would still need it for). Category-page pagination is dropped from this
ticket's scope entirely, not deferred, it has no role once the sitemap path
is built.

### Consequences

1. Good: one discovery mechanism, not two, less code, less to test.
2. Good: the watermark falls out of the discovery mechanism directly
   (`lastmod` is already there), rather than needing to be bolted onto a
   pagination flow that doesn't naturally carry one.
3. Bad: a real deviation from KAN-64's literal ticket text (scope item 2),
   needs this ADR so a future reader understands it was resolved
   deliberately, not missed.
4. Neutral: per-country counts and the `/directory/` browse UI
   (`docs/sources/eu-startups.md`'s other researched surface) remain
   available for a human browsing the site, or for a future enrichment
   ticket that wants to search rather than crawl; this ADR only concerns
   which mechanism *this discovery adapter* uses.

## Related

1. `docs/sources/eu-startups.md`: the research this ADR resolves an
   ambiguity in.
2. KAN-63 (the research ticket), KAN-64 (this decision's ticket).
3. ADR-0007's precedent: a ticket's own text left a real design question
   open, resolved here the same way, documented rather than guessed at
   silently.
