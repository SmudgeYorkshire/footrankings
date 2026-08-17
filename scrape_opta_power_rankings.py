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
"""

import csv
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://dataviz.theanalyst.com/opta-power-rankings/"
OUT_PATH = "opta_power_rankings.csv"

_TABLE_ROW_SEL = "table tbody tr"
_NEXT_BTN_TEXT = ">"
_PAGE_LOAD_WAIT_MS = 8_000
_PAGE_TURN_WAIT_MS = 900


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


def scrape_all_pages(max_pages: int | None = None) -> list[dict]:
    all_rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.goto(URL, wait_until="networkidle", timeout=30_000)
        page.wait_for_selector(_TABLE_ROW_SEL, timeout=_PAGE_LOAD_WAIT_MS)
        time.sleep(1.0)  # let the initial data settle after first paint

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
    return all_rows


def main():
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Scraping Opta Power Rankings from {URL} ...", file=sys.stderr)
    rows = scrape_all_pages(max_pages=max_pages)
    print(f"\nTotal teams scraped: {len(rows)}", file=sys.stderr)

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rank", "team", "rating", "change_7d", "badge_url"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
