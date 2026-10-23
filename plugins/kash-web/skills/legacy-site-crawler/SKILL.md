---
name: legacy-site-crawler
description: Crawl and archive a large, old-style ("web 1.0") website into structured Markdown content plus downloaded images/documents. Use this whenever the user wants to scrape, crawl, mirror, or archive an entire website or "all its pages/branches" — especially old association/municipal/personal sites (SPIP, hand-rolled PHP, static HTML from the 2000s) with hundreds or thousands of pages, no reliable sitemap, and messy navigation. Also use it when the user mentions a specific site URL and asks to "get everything off it", extract its content for reuse, or build a local archive/searchable copy of a site before it disappears. Do NOT use this for scraping a single page or a handful of known URLs (just fetch those directly) or for structured API-backed sites with a clean sitemap and small page count — this skill exists specifically for large, messy, crawl-trap-prone legacy sites.
---

# Legacy site crawler

A polite, resumable crawler for archiving large old-style websites (thousands
of pages, no sitemap worth trusting, heavy nav/sidebar boilerplate repeated
on every page, and sometimes link structures — calendars, session ids — that
trap naive crawlers into an infinite loop). It turns the site into:

- one Markdown file per page (YAML frontmatter + cleaned article text),
  in a directory tree that mirrors the site's URL paths
- a folder of downloaded images/documents, with a record of which page(s)
  referenced each one
- a SQLite state file so a multi-thousand-page crawl can be stopped and
  resumed at any point without re-fetching what's already done

The crawler lives at `scripts/crawl.py` in this skill and only needs
`requirements.txt` installed (`pip install -r scripts/requirements.txt`).
Fetching goes through [Scrapling](https://github.com/D4Vinci/Scrapling)
rather than a plain HTTP client: its default `Fetcher` is a fast,
lightweight HTTP engine, and `--engine stealth` switches to
`StealthyFetcher`, which drives a real browser to get past Cloudflare/WAF
challenges — useful because plenty of old, otherwise-static sites now sit
behind modern anti-bot protection even though their content hasn't changed
since 2004. If you plan to ever use `--engine stealth`, run
`scrapling install` once after `pip install` to fetch its browser
dependencies.

## Why this needs a strategy, not just a script

A 2000+ page site from this era almost never has a trustworthy sitemap, so
discovery has to happen by following links (breadth-first from the home
page). Three things go wrong if you don't plan for them, and this script
handles all three:

1. **Crawler traps.** Calendar/agenda widgets and similar generators link to
   "next month" forever; session ids in query strings make every page look
   infinite in the number of unique URLs. The script normalizes URLs
   (drops session/tracking params, sorts query params) so equivalent pages
   dedupe, and caps how many pages it will queue per "path + query shape"
   (`--max-per-template`, default 300) so a calendar can't eat the whole
   crawl budget.
2. **Content vs. boilerplate.** Every page repeats the same nav/header/
   footer/sidebar HTML; naively dumping `<body>` text buries the actual
   article in menu noise. The script tries a list of common content-area
   selectors first (`#contenu`, `#content`, `main`, `article`, ...) and
   falls back to `<body>` with nav/header/footer/script/style stripped.
3. **A multi-hour crawl will get interrupted.** Container restarts, network
   blips, or you just wanting to stop and look at partial results. State is
   a SQLite file in `--output-dir`; rerunning the same command with the same
   `--output-dir` (and no URL) picks up exactly where it left off.

## Recommended workflow

1. **Check you're actually allowed to fetch the site from here, and figure
   out which kind of 403 you're looking at if you get one.** Run one
   `curl -sI <url>` (or try step 2 with `--max-pages 1`) before committing
   to a real crawl. Two different problems both show up as "403" and need
   opposite fixes:
   - **The sandbox's own network policy blocks the host** — a 403 from the
     egress proxy/gateway itself, before the request ever reaches the
     target site (in this kind of environment, check
     `curl -sS "$HTTPS_PROXY/__agentproxy/status"` for `recentRelayFailures`
     naming the host). No `--engine` or retry fixes this; it has to be
     fixed in the environment's network settings.
   - **The site itself is blocking the request** — anti-bot/WAF (Cloudflare
     challenge, etc.) or a plain robots.txt disallow. This is what
     `--engine stealth` is for (see above); a robots.txt disallow should
     just be respected, not worked around.

2. **Small dry run first.** The default `--max-pages` is 20 specifically so
   a first invocation is cheap to eyeball:

   ```
   python3 scripts/crawl.py https://example.org/ \
     --output-dir ./crawl-data \
     --user-agent "legacy-site-crawler/1.0 (+contact: you@example.com; archival crawl)"
   ```

   Look at `crawl-data/content/**/*.md` — is the title right? Is the body
   the actual article, or did a content-selector miss and it's full of menu
   links? Check `crawl-data/report.json` for how many pages are queued vs.
   done vs. failed. Adjust `CONTENT_SELECTORS` in the script if this
   particular site's template needs a selector that isn't in the default
   list (view-source on one article page to find its container id/class).

3. **Set the real user agent.** Always replace the contact-email placeholder
   in `--user-agent` with something real before a full crawl — it's how the
   site owner can reach you if the crawl is causing them trouble, and it's
   the polite/expected thing to do when hitting someone else's server
   thousands of times.

4. **Scale up.** Once the dry run looks right, rerun with a realistic
   `--max-pages` (or a very large number to mean "until the frontier is
   empty") and a `--rate` that won't strain a small/old server — the
   default of 1 request/second is a reasonable starting point; there is no
   concurrency by design; this is for archival correctness over speed, not
   the other way around.

5. **Resume as needed.** If the crawl stops (Ctrl-C, timeout, crash), just
   rerun the exact same command without the URL argument — it will read the
   seed URL and all state back out of `--output-dir/state.sqlite` and keep
   going from the frontier. Nothing already marked `done` is re-fetched.

6. **Re-run is safe.** Re-running against the same `--output-dir` after the
   crawl finished (e.g. to pick up a couple of pages that failed
   transiently) just resumes an empty-looking frontier — failed pages stay
   `failed` rather than being retried automatically, so if you want to
   retry failures specifically, query `state.sqlite` for `status='failed'`
   and re-seed those URLs, or inspect `error` column to see why they failed
   first (some failures are legitimate, e.g. a genuinely dead link).

## Inspecting results

`state.sqlite` (in `--output-dir`) has three tables worth querying directly
when you need something the Markdown/JSON output doesn't show:

- `pages` — every URL seen, its `status` (`queued`/`done`/`failed`/
  `skipped`), `depth`, and `content_path`
- `assets` — every downloaded image/document, its local path, size, and
  content type
- `asset_refs` — which page(s) linked to which asset (an asset can be
  referenced from multiple pages; it's only downloaded once)

`report.json` is rewritten periodically during the crawl and once at the
end — a quick way to see progress (`pages: {done, failed, skipped,
queued}`, `assets`, `asset_bytes`) without touching SQLite.

## Flags reference

| Flag | Default | Purpose |
|---|---|---|
| `start_url` | — | Seed URL; omit when resuming |
| `--output-dir` | required | Where content/assets/state/debug go |
| `--max-pages` | 20 | Safety valve — raise once the dry run looks good |
| `--max-depth` | 12 | Don't follow links deeper than this from the seed |
| `--max-per-template` | 300 | Crawler-trap guard (see above) |
| `--rate` | 1.0 req/s | Politeness throttle, no concurrency |
| `--timeout` | 20s | Per-request timeout |
| `--user-agent` | placeholder | **Replace the contact email before a real crawl** |
| `--no-assets` | off | Skip image/document downloads, text only |
| `--engine` | `http` | `http` (fast) or `stealth` (browser-based Cloudflare/WAF bypass, slower) |

## What this skill deliberately does not do

- It does not mirror raw HTML by default (only the parsed/cleaned Markdown
  is kept long-term; raw HTML is saved to `debug/` only for pages that
  failed to parse, to help you fix the content-selector list).
- It does not bypass `robots.txt` — disallowed pages are recorded as
  `skipped`, not fetched.
- It does not use concurrency — this is intentional; an old, possibly
  volunteer-run server is the target audience, not a CDN-backed site built
  to take load.
