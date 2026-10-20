# -*- coding: utf-8 -*-
"""Smoke: dev server + report 65 loads in a real browser."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5510"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{BASE}/#/report/65", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(4000)
    body = page.inner_text("body")
    print("title:", page.title())
    print("has 具体用例:", "具体用例" in body)
    print("case cards:", page.locator(".case-card").count())
    print("review buttons:", page.locator(".review-action-btn").count())
    print("console errors:", errors[:5])
    browser.close()
