"""
Scrapes the full global Opta Power Rankings table from
https://dataviz.theanalyst.com/opta-power-rankings/ (the public dataviz
widget theanalyst.com itself embeds — updates daily Mon-Fri). No API key
works for the underlying Stats Perform feed from outside their own
site (session/referrer-gated), so this drives a real headless browser
and reads the rendered table instead, exactly like the page's own users
would see it.

Writes the full ~13,800-team list to opta_power_rankings.csv (rank,
team, rating, change_7d, badge_url) -- the single source both
update_ratings_from_opta.py (matches it against our 54 leagues' ratings
CSVs) and the Opta Rankings page's "complete ranking" table read from.

Also writes opta_power_rankings_meta.json with the date Opta itself
states the ranking was last updated (the page footer reads "Updates
daily Monday to Friday. Last updated <date>.") alongside when this site
last ran the scrape -- the Opta date is the one that actually answers
"how fresh is this data", since our own scrape can succeed on a day
Opta's own numbers didn't move (or, if a scheduled run is ever missed,
silently be a day behind without the Opta date's mismatch to flag it).
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

URL = "https://dataviz.theanalyst.com/opta-power-rankings/"
OUT_PATH = "opta_power_rankings.csv"
META_PATH = "opta_power_rankings_meta.json"

_TABLE_ROW_SEL = "table tbody tr"
_NEXT_BTN_TEXT = ">"
_PAGE_LOAD_WAIT_MS = 8_000
_PAGE_TURN_WAIT_MS = 900
_LAST_UPDATED_RE = re.compile(r"Last updated\s+([A-Za-z]+ \d{1,2},\s*\d{4})")


def _extract_opta_last_updated(page) -> str | None:
    """Parses Opta's own "Last updated <Mon DD, YYYY>" footer text into
    an ISO date string, or None if the page's wording ever changes."""
    text = page.eval_on_selector_all(
        "*",
        """
        (els) => {
            const el = els.find(e => e.children.length === 0 && /last updated/i.test(e.textContent||''));
            return el ? el.textContent.trim() : null;
        }
        """,
    )
    if not text:
        return None
    m = _LAST_UPDATED_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _read_current_page(page) -> list[dict]:
    rows = page.eval_on_selector_all(
        _TABLE_ROW_SEL,
        """
        (trs) => trs.map(tr => {
            const cells = tr.querySelectorAll('td');
            if (cells.length < 4) return null;
            const img = cells[1].querySelector('img');
            const nameDiv = cells[1].querySelector('div[style*="font-family"]');
            return {
                rank: cells[0].textContent.trim(),
                team: (nameDiv || cells[1]).textContent.trim(),
                rating: cells[2].textContent.trim(),
                change_7d: cells[3].textContent.trim(),
                badge_url: img ? img.getAttribute('src') : '',
            };
        }).filter(Boolean)
        """,
    )
    return rows


def _current_page_number(page) -> int | None:
    text = page.eval_on_selector_all(
        "*",
        """
        (els) => {
            const el = els.find(e => e.children.length === 0 && /^\\d+\\s+of\\s+\\d+$/.test((e.textContent||'').trim()));
            return el ? el.textContent.trim() : null;
        }
        """,
    )
    if not text:
        return None
    return int(text.split()[0])


def scrape_all_pages(max_pages: int | None = None) -> tuple[list[dict], str | None]:
    all_rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.goto(URL, wait_until="networkidle", timeout=30_000)
        page.wait_for_selector(_TABLE_ROW_SEL, timeout=_PAGE_LOAD_WAIT_MS)
        time.sleep(1.0)  # let the initial data settle after first paint

        opta_last_updated = _extract_opta_last_updated(page)

        page_num = _current_page_number(page)
        total_pages = None
        pager_text = page.eval_on_selector_all(
            "*",
            """
            (els) => {
                const el = els.find(e => e.children.length === 0 && /^\\d+\\s+of\\s+\\d+$/.test((e.textContent||'').trim()));
                return el ? el.textContent.trim() : null;
            }
            """,
        )
        if pager_text:
            total_pages = int(pager_text.split()[-1])
        if max_pages:
            total_pages = min(total_pages or max_pages, max_pages)

        seen_first_team = None
        page_count = 0
        while True:
            page_count += 1
            rows = _read_current_page(page)
            if not rows:
                print(f"  page {page_count}: no rows found, stopping", file=sys.stderr)
                break
            all_rows.extend(rows)
            print(f"  page {page_count}/{total_pages or '?'}: {len(rows)} teams "
                  f"(first: {rows[0]['team']} #{rows[0]['rank']})", file=sys.stderr)

            if total_pages and page_count >= total_pages:
                break

            clicked = page.evaluate(
                """
                () => {
                    const btns = Array.from(document.querySelectorAll('button, [role=button], span, a'));
                    const el = btns.find(b => b.textContent.trim() === '>');
                    if (!el) return false;
                    el.click();
                    return true;
                }
                """
            )
            if not clicked:
                print("  no next-page button found, stopping", file=sys.stderr)
                break
            time.sleep(_PAGE_TURN_WAIT_MS / 1000)

        browser.close()
    return all_rows, opta_last_updated


def main():
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Scraping Opta Power Rankings from {URL} ...", file=sys.stderr)
    rows, opta_last_updated = scrape_all_pages(max_pages=max_pages)
    print(f"\nTotal teams scraped: {len(rows)}", file=sys.stderr)
    print(f"Opta's own last-updated date: {opta_last_updated or '(not found on page)'}", file=sys.stderr)

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rank", "team", "rating", "change_7d", "badge_url"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUT_PATH}", file=sys.stderr)

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "opta_last_updated": opta_last_updated,
            "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "team_count": len(rows),
        }, f, indent=2)
    print(f"Wrote {META_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
