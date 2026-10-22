"""Browser smoke test: loads every page, clicks through the main interactions and fails on console errors.

    python tests/e2e_ui.py http://localhost:8010 [screenshot_dir]
Needs `pip install playwright` and Google Chrome. Works against `make serve` (8010) or `make static` (8011).
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

url = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010").rstrip("/")
out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if out:
    out.mkdir(parents=True, exist_ok=True)
errors: list[str] = []


def on_console(m) -> None:
    if m.type != "error":
        return
    if "/api/health" in ((m.location or {}).get("url") or ""):
        return  # static server has no API; the page probes it once
    errors.append(m.text)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1500, "height": 950}, reduced_motion="reduce")
    page.on("console", on_console)
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 00 home: the patient map
    page.goto(f"{url}/index.html")
    page.wait_for_selector("#pmap")
    page.wait_for_function("document.querySelector('#pmap').dataset.settled === 'true'", timeout=60000)
    assert page.locator("#legend button").count() == 7, "7 biomarker subgroups expected"
    assert page.locator(".av").count() >= 10
    page.click('[data-mode="study"]')
    assert page.locator("#legend button").count() == 4
    page.locator("#legend button").first.click()
    assert page.locator("#legend button[aria-pressed='true']").count() == 1
    assert page.locator(".pi").count() == 0, "home has no patient rail"
    if out:
        page.screenshot(path=str(out / "home.png"))

    # 01 data input
    page.click('#nav a[data-file="sources.html"]')
    page.wait_for_selector(".src-card")
    assert page.locator(".pi").count() == 36, "36 demo patients expected"
    assert page.locator(".src-card").count() == 5
    page.click('[data-f="g12c"]')
    assert 0 < page.locator(".pi").count() < 36
    page.click('[data-f="all"]')
    page.locator(".pi").nth(2).click()
    page.wait_for_function("document.querySelector('.pi[aria-pressed=\"true\"]') === document.querySelectorAll('.pi')[2]")
    assert "p=" in page.url
    if out:
        page.screenshot(path=str(out / "sources.png"))

    # 02 trial match (patient carried in the URL)
    page.click('#nav a[data-file="match.html"]')
    page.wait_for_selector(".mrow")
    assert page.locator(".pi[aria-pressed='true']").count() == 1
    n_rows = page.locator(".mrow").count()
    assert n_rows >= 10, n_rows
    assert page.locator("#thmap").count() == 1
    assert page.locator("#hot-table tbody tr").count() >= 8
    page.wait_for_selector(".mrow.open .mbody")

    # what-if: resolve the first Unknown on an open row that has controls
    opened = False
    for i in range(min(n_rows, 12)):
        row = page.locator(".mrow").nth(i)
        if "open" not in (row.get_attribute("class") or ""):
            row.locator(".mhead").click()
        sel = page.locator(".mrow.open select[data-fact]")
        if sel.count():
            before = page.locator(".mrow.open .counts .u b").inner_text()
            sel.first.select_option(index=1)
            after = page.locator(".mrow.open .counts .u b").inner_text()
            assert int(after) <= int(before), (before, after)
            assert page.locator(".mrow.open .vchip").inner_text().startswith("what-if")
            opened = True
            if out:
                page.screenshot(path=str(out / "whatif.png"))
            break
    assert opened, "no row with a what-if control found"

    # hotspot subgroup switch and province hover
    page.select_option("#hot-pop", "mcrc")
    assert "mCRC, all" in page.locator("#hot-method").inner_text()
    box = page.locator("#thmap").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.45)
    page.mouse.move(box["x"] + box["width"] * 0.52, box["y"] + box["height"] * 0.5)

    # 04 referral keeps the what-if and the open trial
    page.locator(".mrow.open .acts a.btn").first.click()
    page.wait_for_selector(".doc")
    doc = page.locator(".doc").inner_text().lower()
    assert "review-ready referral" in doc and "what-if" in doc
    page.click("#nav a[data-file='match.html']")
    page.wait_for_selector(".mrow.open")
    page.click("#reset-wi")
    assert not page.locator(".mrow.open .vchip").inner_text().startswith("what-if")

    # 03 embedding: map and hover tooltip
    page.click('#nav a[data-file="embed.html"]')
    page.wait_for_selector("#map")
    assert page.locator(".hits li").count() >= 5
    box = page.locator("#map").bounding_box()
    for dx in range(0, 200, 8):
        page.mouse.move(box["x"] + box["width"] * 0.35 + dx, box["y"] + box["height"] * 0.5)
    if out:
        page.screenshot(path=str(out / "embed.png"))

    # 05 evidence
    page.click('#nav a[data-file="evidence.html"]')
    page.wait_for_selector(".inv")
    assert page.locator(".inv tbody tr").count() >= 7

    # 06 evaluation: recall bars, schedules, matched-times chart reacts to the selected patient
    page.click('#nav a[data-file="evaluation.html"]')
    page.wait_for_selector(".sched")
    assert page.locator(".sched tbody tr").count() >= 5
    assert page.locator("#tl circle").count() >= 1
    page.locator(".pi").nth(1).click()
    page.wait_for_selector("#tl circle.sel")
    if out:
        page.screenshot(path=str(out / "evaluation.png"))
    b.close()

assert not errors, errors
print("ui smoke test passed")
