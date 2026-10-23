#!/usr/bin/env python3
"""Polite, resumable BFS crawler for large "web 1.0" style sites.

Designed for old, unindexed sites (SPIP, hand-rolled PHP, static HTML
dumps, ...) that have hundreds to thousands of pages, no sitemap worth
trusting, and occasional link structures that trap naive crawlers
(calendars, session ids in the URL, etc).

Output layout under --output-dir:
  state.sqlite   crawl state: page queue/status, discovered assets
  content/...    one .md file per page, mirroring the URL path, with
                 YAML frontmatter (title, source_url, crawled_at, ...)
  assets/...     downloaded images/documents, named by content hash
  debug/...      raw HTML saved only for pages that failed to parse
  report.json    progress / summary, rewritten periodically

Run `python3 crawl.py --help` for all flags. See the accompanying
SKILL.md for the recommended workflow (small dry run first, then a
full crawl, resumed as many times as needed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import sqlite3
import sys
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import (
    parse_qsl,
    urldefrag,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

from bs4 import BeautifulSoup, Comment
from scrapling.fetchers import Fetcher, StealthyFetcher

DEFAULT_USER_AGENT = (
    "legacy-site-crawler/1.0 "
    "(+contact: REPLACE_WITH_YOUR_EMAIL; one-off archival crawl, see robots.txt)"
)

# Query-string keys that identify a browsing session rather than a distinct
# page. Stripping them is what lets the crawler recognize that
# "?PHPSESSID=abc&article=12" and "?PHPSESSID=xyz&article=12" are the same
# page, instead of queuing a fresh copy forever.
TRACKING_PARAMS = {
    "phpsessid", "sessid", "sid", "session", "sessionid",
    "fbclid", "gclid", "msclkid",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
}

ASSET_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rtf",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff",
}

SKIP_EXTENSIONS = {
    ".css", ".js", ".ico", ".mp3", ".mp4", ".avi", ".mov", ".exe", ".woff",
    ".woff2", ".ttf", ".eot", ".svg", ".xml", ".json",
}

# Tried in order; the first match is treated as "the article", which lets us
# throw away nav/sidebar/footer boilerplate that these old templates repeat
# on every single page. If nothing matches we fall back to <body> minus the
# structural tags stripped in NOISE_TAGS.
CONTENT_SELECTORS = [
    "#contenu", "#content", "#corps", "#main-content", "#page-content",
    "main", "article", ".contenu", ".content", ".article", ".corps",
    "#article", "#texte",
]

NOISE_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "form",
    "noscript", "iframe",
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# URL handling
# --------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """Canonicalize a URL so equivalent pages dedupe to the same key.

    Drops the fragment, lowercases scheme/host, and removes tracking /
    session query params (sorting what's left) so the same page reached
    via two different session ids collapses to one queue entry.
    """
    url, _frag = urldefrag(url)
    parts = urlsplit(url)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    query_pairs = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    )
    query = urlencode(query_pairs)
    return urlunsplit((scheme, netloc, path, query, ""))


def path_template(normalized_url: str) -> str:
    """Group URLs that share a path and query *shape* (ignoring values).

    Calendar/agenda pages on these old sites often generate an unbounded
    stream of links that differ only in a date value
    (?year=2001&month=1, ?year=2001&month=2, ...). Capping how many pages
    per template we'll enqueue (see --max-per-template) stops that from
    silently turning a 2000-page crawl into an infinite one.
    """
    parts = urlsplit(normalized_url)
    keys = tuple(sorted(k for k, _ in parse_qsl(parts.query)))
    return f"{parts.path}?{','.join(keys)}" if keys else parts.path


def same_domain(url: str, root_netloc: str) -> bool:
    return urlsplit(url).netloc.lower() == root_netloc


def sanitize_segment(segment: str, max_len: int = 120) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "_", segment).strip("_")
    return (segment or "root")[:max_len]


def content_path_for(output_dir: Path, normalized_url: str) -> Path:
    parts = urlsplit(normalized_url)
    path = parts.path
    if path.endswith("/") or path == "":
        path += "index"
    root, _ext = path.rsplit("/", 1)[0], path  # keep original, extension stripped below
    segments = [sanitize_segment(s) for s in path.strip("/").split("/") if s]
    if not segments:
        segments = ["index"]
    else:
        # strip a trailing .html/.php/etc so we don't end up with foo.php.md
        last = segments[-1]
        segments[-1] = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", last) or "index"
    if parts.query:
        segments.append(sanitize_segment(parts.query, max_len=80))
    return output_dir / "content" / Path(*segments).with_suffix(".md")


def asset_local_path(output_dir: Path, url: str, content_type: str | None) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    ext = Path(urlsplit(url).path).suffix.lower()
    if not ext and content_type:
        guess = {
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
        }.get(content_type.split(";")[0].strip())
        ext = guess or ""
    return output_dir / "assets" / f"{digest}{ext}"


# --------------------------------------------------------------------------
# Content extraction
# --------------------------------------------------------------------------

def extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())
    h1 = soup.find("h1")
    if h1:
        return " ".join(h1.get_text().split())
    return ""


def find_main_node(soup: BeautifulSoup):
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node and len(node.get_text(strip=True)) > 80:
            return node
    return soup.body or soup


def extract_main_text(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    node = find_main_node(soup)

    lines: list[str] = []
    for el in node.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "blockquote"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name in {"h1", "h2", "h3", "h4"}:
            level = "#" * (int(el.name[1]) + 1)
            lines.append(f"\n{level} {text}\n")
        elif el.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)
    if not lines:
        # last resort: raw text, still better than nothing
        text = " ".join(node.get_text(" ", strip=True).split())
        if text:
            lines.append(text)
    return "\n\n".join(lines).strip()


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_markdown(path: Path, *, title: str, source_url: str, depth: int,
                    http_status: int, crawled_at: str, asset_paths: list[str],
                    body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = [
        "---",
        f'title: "{yaml_escape(title)}"',
        f'source_url: "{yaml_escape(source_url)}"',
        f"crawled_at: {crawled_at}",
        f"depth: {depth}",
        f"http_status: {http_status}",
    ]
    if asset_paths:
        frontmatter.append("assets:")
        frontmatter += [f'  - "{yaml_escape(p)}"' for p in asset_paths]
    frontmatter.append("---\n")
    path.write_text("\n".join(frontmatter) + "\n" + body + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# State (sqlite)
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    depth INTEGER NOT NULL,
    path_template TEXT,
    discovered_at TEXT,
    fetched_at TEXT,
    http_status INTEGER,
    error TEXT,
    content_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);

CREATE TABLE IF NOT EXISTS assets (
    url TEXT PRIMARY KEY,
    local_path TEXT,
    content_type TEXT,
    bytes INTEGER,
    downloaded_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS asset_refs (
    asset_url TEXT NOT NULL,
    page_url TEXT NOT NULL,
    PRIMARY KEY (asset_url, page_url)
);
"""


class State:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def seed(self, url: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO pages(url, status, depth, path_template, discovered_at) "
            "VALUES (?, 'queued', 0, ?, ?)",
            (url, path_template(url), now_iso()),
        )
        self.conn.commit()

    def enqueue(self, url: str, depth: int) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO pages(url, status, depth, path_template, discovered_at) "
            "VALUES (?, 'queued', ?, ?, ?)",
            (url, depth, path_template(url), now_iso()),
        )
        return cur.rowcount > 0

    def template_count(self, template: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM pages WHERE path_template = ?", (template,)
        ).fetchone()
        return row[0]

    def next_queued(self):
        return self.conn.execute(
            "SELECT id, url, depth FROM pages WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()

    def mark_done(self, page_id: int, http_status: int, content_path: str) -> None:
        self.conn.execute(
            "UPDATE pages SET status='done', fetched_at=?, http_status=?, content_path=? "
            "WHERE id=?",
            (now_iso(), http_status, content_path, page_id),
        )
        self.conn.commit()

    def mark_failed(self, page_id: int, error: str, http_status: int | None = None) -> None:
        self.conn.execute(
            "UPDATE pages SET status='failed', fetched_at=?, http_status=?, error=? WHERE id=?",
            (now_iso(), http_status, error[:500], page_id),
        )
        self.conn.commit()

    def mark_skipped(self, page_id: int, reason: str) -> None:
        self.conn.execute(
            "UPDATE pages SET status='skipped', fetched_at=?, error=? WHERE id=?",
            (now_iso(), reason[:500], page_id),
        )
        self.conn.commit()

    def record_asset(self, asset_url: str, page_url: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO asset_refs(asset_url, page_url) VALUES (?, ?)",
            (asset_url, page_url),
        )
        self.conn.commit()

    def asset_known(self, asset_url: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM assets WHERE url=?", (asset_url,)
        ).fetchone()

    def save_asset(self, asset_url: str, local_path: str | None, content_type: str | None,
                    nbytes: int | None, error: str | None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO assets(url, local_path, content_type, bytes, downloaded_at, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (asset_url, local_path, content_type, nbytes, now_iso(), error),
        )
        self.conn.commit()

    def counts(self) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM pages GROUP BY status"
        ).fetchall()
        result = {status: n for status, n in rows}
        result["assets"] = self.conn.execute(
            "SELECT COUNT(*) FROM assets WHERE local_path IS NOT NULL"
        ).fetchone()[0]
        result["asset_bytes"] = self.conn.execute(
            "SELECT COALESCE(SUM(bytes), 0) FROM assets"
        ).fetchone()[0]
        return result


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Crawler
# --------------------------------------------------------------------------

@dataclass
class Config:
    start_url: str
    output_dir: Path
    max_pages: int
    max_depth: int
    max_per_template: int
    rate: float
    user_agent: str
    timeout: float
    download_assets: bool
    engine: str


class Crawler:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.output_dir = cfg.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "content").mkdir(exist_ok=True)
        (self.output_dir / "assets").mkdir(exist_ok=True)
        (self.output_dir / "debug").mkdir(exist_ok=True)
        self.state = State(self.output_dir / "state.sqlite")
        self.root_netloc = urlsplit(cfg.start_url).netloc.lower()
        self.robots = urllib.robotparser.RobotFileParser()
        robots_url = urlunsplit((urlsplit(cfg.start_url).scheme, self.root_netloc, "/robots.txt", "", ""))
        try:
            self.robots.set_url(robots_url)
            self.robots.read()
            log(f"robots.txt loaded from {robots_url}")
        except Exception as exc:
            log(f"could not fetch robots.txt ({exc}); proceeding as if everything is allowed")
        self._stop = False
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        log("interrupt received, finishing current page then stopping (state is saved; rerun to resume)")
        self._stop = True

    def allowed(self, url: str) -> bool:
        try:
            return self.robots.can_fetch(self.cfg.user_agent, url)
        except Exception:
            return True

    def _fetch_page(self, url: str):
        """Fetch a page HTML through the configured Scrapling engine.

        The plain HTTP engine (Fetcher) is fast and enough for most of
        these old sites. --engine stealth switches to StealthyFetcher,
        which drives a real browser to get past Cloudflare/WAF challenges
        — reach for it only if a dry run comes back with a 403 or a
        challenge page, since it's much slower and heavier per request.
        """
        if self.cfg.engine == "stealth":
            return StealthyFetcher.fetch(
                url,
                useragent=self.cfg.user_agent,
                timeout=self.cfg.timeout,
                solve_cloudflare=True,
                headless=True,
            )
        return Fetcher.get(
            url,
            headers={"User-Agent": self.cfg.user_agent},
            timeout=self.cfg.timeout,
            follow_redirects=True,
        )

    def _fetch_asset(self, url: str):
        # Assets are static files; the plain HTTP engine is enough even
        # when the surrounding pages need --engine stealth to render.
        return Fetcher.get(
            url,
            headers={"User-Agent": self.cfg.user_agent},
            timeout=self.cfg.timeout,
            follow_redirects=True,
        )

    def run(self) -> None:
        self.state.seed(self.cfg.start_url)
        processed_this_run = 0
        last_report = 0.0

        while not self._stop:
            counts = self.state.counts()
            done = counts.get("done", 0) + counts.get("failed", 0) + counts.get("skipped", 0)
            if done >= self.cfg.max_pages:
                log(f"reached --max-pages ({self.cfg.max_pages}); stopping. Raise the limit and rerun to continue.")
                break

            row = self.state.next_queued()
            if row is None:
                log("frontier empty, crawl complete")
                break
            page_id, url, depth = row

            if not self.allowed(url):
                self.state.mark_skipped(page_id, "disallowed by robots.txt")
                continue
            if depth > self.cfg.max_depth:
                self.state.mark_skipped(page_id, f"depth {depth} exceeds --max-depth")
                continue

            self.fetch_page(page_id, url, depth)
            processed_this_run += 1
            time.sleep(max(0.0, 1.0 / self.cfg.rate))

            if time.time() - last_report > 10:
                self.write_report()
                last_report = time.time()

        self.write_report()

    def fetch_page(self, page_id: int, url: str, depth: int) -> None:
        try:
            resp = self._fetch_page(url)
        except Exception as exc:
            log(f"FAIL  {url}  ({exc})")
            self.state.mark_failed(page_id, str(exc))
            return

        content_type = resp.headers.get("content-type", "")
        if resp.status >= 400:
            log(f"HTTP{resp.status} {url}")
            self.state.mark_failed(page_id, f"HTTP {resp.status}", resp.status)
            return

        if "text/html" not in content_type:
            self.state.mark_skipped(page_id, f"non-HTML content-type: {content_type}")
            return

        final_url = normalize_url(resp.url)
        try:
            soup = BeautifulSoup(resp.html_content, "lxml")
        except Exception as exc:
            debug_path = self.output_dir / "debug" / f"{page_id}.html"
            debug_path.write_text(resp.html_content, encoding="utf-8", errors="replace")
            self.state.mark_failed(page_id, f"parse error: {exc}")
            return

        title = extract_title(soup) or url

        # Link/asset discovery must happen on the pristine tree: extract_main_text
        # strips nav/header/footer to isolate the article body, but on these sites
        # the menu in that nav/header is often the only path to whole sections of
        # the site, so it has to be read before it gets thrown away.
        self.enqueue_links(soup, resp.url, depth)
        asset_paths = self.collect_and_download_assets(soup, resp.url, final_url) if self.cfg.download_assets else []

        try:
            body = extract_main_text(soup)
        except Exception as exc:
            debug_path = self.output_dir / "debug" / f"{page_id}.html"
            debug_path.write_text(resp.html_content, encoding="utf-8", errors="replace")
            self.state.mark_failed(page_id, f"extraction error: {exc}")
            return

        content_path = content_path_for(self.output_dir, final_url)
        write_markdown(
            content_path,
            title=title,
            source_url=final_url,
            depth=depth,
            http_status=resp.status,
            crawled_at=now_iso(),
            asset_paths=asset_paths,
            body=body,
        )
        self.state.mark_done(page_id, resp.status, str(content_path.relative_to(self.output_dir)))
        log(f"OK    depth={depth} {final_url} -> {content_path.relative_to(self.output_dir)}")

    def enqueue_links(self, soup: BeautifulSoup, base_url: str, depth: int) -> None:
        seen_on_page = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            normalized = normalize_url(absolute)
            if normalized in seen_on_page:
                continue
            seen_on_page.add(normalized)
            if not same_domain(normalized, self.root_netloc):
                continue
            ext = Path(urlsplit(normalized).path).suffix.lower()
            if ext in SKIP_EXTENSIONS or ext in ASSET_EXTENSIONS:
                continue  # assets are handled separately, other statics are not useful content

            template = path_template(normalized)
            if self.state.template_count(template) >= self.cfg.max_per_template:
                continue  # crawler-trap guard: e.g. an endless calendar/agenda widget

            self.state.enqueue(normalized, depth + 1)

    def collect_and_download_assets(self, soup: BeautifulSoup, base_url: str, page_url: str) -> list[str]:
        found: list[str] = []
        candidates = []
        for img in soup.find_all("img", src=True):
            candidates.append(img["src"])
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if Path(urlsplit(href).path).suffix.lower() in ASSET_EXTENSIONS:
                candidates.append(href)

        for raw in candidates:
            absolute = urljoin(base_url, raw.strip())
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            if not same_domain(absolute, self.root_netloc):
                continue
            asset_url, _ = urldefrag(absolute)
            self.state.record_asset(asset_url, page_url)
            local = self.download_asset(asset_url)
            if local:
                found.append(local)
        return found

    def download_asset(self, asset_url: str) -> str | None:
        existing = self.state.asset_known(asset_url)
        if existing and existing["local_path"]:
            return existing["local_path"]
        try:
            resp = self._fetch_asset(asset_url)
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")
        except Exception as exc:
            self.state.save_asset(asset_url, None, None, None, str(exc))
            return None
        content_type = resp.headers.get("content-type")
        local_path = asset_local_path(self.output_dir, asset_url, content_type)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(resp.body)
        rel = str(local_path.relative_to(self.output_dir))
        self.state.save_asset(asset_url, rel, content_type, len(resp.body), None)
        time.sleep(max(0.0, 1.0 / self.cfg.rate))
        return rel

    def write_report(self) -> None:
        counts = self.state.counts()
        report = {
            "generated_at": now_iso(),
            "start_url": self.cfg.start_url,
            "pages": counts,
            "output_dir": str(self.output_dir),
        }
        (self.output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def parse_args(argv=None) -> Config:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("start_url", nargs="?", help="Seed URL (only needed the first time; a resumed crawl reads it from state.sqlite)")
    p.add_argument("--output-dir", required=True, type=Path, help="Directory to write content/assets/state into")
    p.add_argument("--max-pages", type=int, default=20,
                   help="Stop after this many pages are done/failed/skipped (default 20 — a safe dry run; raise it once you like what you see)")
    p.add_argument("--max-depth", type=int, default=12, help="Don't follow links deeper than this from the seed")
    p.add_argument("--max-per-template", type=int, default=300,
                   help="Cap pages sharing the same path+query-shape, to defuse calendar/agenda-style crawler traps")
    p.add_argument("--rate", type=float, default=1.0, help="Max requests per second (default 1 — stay polite on a small/old server)")
    p.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Replace the contact email placeholder before a real crawl")
    p.add_argument("--no-assets", action="store_true", help="Skip downloading images/documents, text content only")
    p.add_argument("--engine", choices=["http", "stealth"], default="http",
                   help="Fetch engine: 'http' (fast, default) or 'stealth' (real-browser bypass for "
                        "Cloudflare/WAF-protected sites — try this only if a dry run with 'http' comes "
                        "back 403 or shows a challenge page instead of real content)")
    args = p.parse_args(argv)

    db_exists = (args.output_dir / "state.sqlite").exists()
    if not db_exists and not args.start_url:
        p.error("start_url is required the first time (no existing state.sqlite in --output-dir)")

    return Config(
        start_url=args.start_url or "",
        output_dir=args.output_dir,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_per_template=args.max_per_template,
        rate=args.rate,
        user_agent=args.user_agent,
        timeout=args.timeout,
        download_assets=not args.no_assets,
        engine=args.engine,
    )


def main(argv=None) -> int:
    cfg = parse_args(argv)
    db_path = cfg.output_dir / "state.sqlite"
    if db_path.exists() and not cfg.start_url:
        # resuming: recover the seed url from the first-ever row for logging only
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT url FROM pages ORDER BY id LIMIT 1").fetchone()
        cfg.start_url = row[0] if row else "(unknown)"
        log(f"resuming crawl of {cfg.start_url} from {db_path}")
    else:
        log(f"starting crawl of {cfg.start_url}")

    crawler = Crawler(cfg)
    crawler.run()
    counts = crawler.state.counts()
    log(f"summary: {json.dumps(counts)}")
    log(f"report written to {crawler.output_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
