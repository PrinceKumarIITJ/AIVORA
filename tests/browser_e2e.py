"""Real-browser vertical slice against a temporary database and actual HTTP server.

Run with a Python environment containing AIVORA dependencies and Playwright.
Uses Chrome if installed; otherwise Playwright Chromium. Never touches live company data.
"""
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright
from aivora.api import create_app
from aivora.config import Settings


def run():
    errors = []
    with tempfile.TemporaryDirectory(prefix="aivora-browser-") as temp:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        app = create_app(Settings(database_url="sqlite:///" + (Path(temp) / "test.db").as_posix(), origin=origin))
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        if not server.started:
            raise RuntimeError("Temporary HTTP server did not start")
        try:
            with sync_playwright() as p:
                chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
                browser = p.chromium.launch(headless=True, **({"executable_path": str(chrome)} if chrome.exists() else {}))
                owner_context = browser.new_context(viewport={"width": 1440, "height": 1000})
                owner = owner_context.new_page()
                owner.on("pageerror", lambda error: errors.append(str(error)))
                owner.goto(origin)
                owner.get_by_role("button", name="Create workspace", exact=True).click()
                owner.get_by_label("Your name").fill("Taylor Owner")
                owner.get_by_label("Organization name").fill("Browser Test Studio")
                owner.get_by_label("Industry").fill("Design")
                owner.get_by_label("Work email").fill("owner@browser.test")
                owner.get_by_label("Password", exact=True).fill("browser-test-password-123")
                owner.locator("#auth-form button[type=submit]").click()
                expect(owner.get_by_role("heading", name="Good to see you, Taylor.")).to_be_visible()
                owner.locator('[data-nav="knowledge"]').click()
                owner.get_by_role("button", name="Add document").click()
                owner.get_by_label("Document title").fill("Leave handbook")
                owner.locator('input[type="file"]').set_input_files({"name": "leave.md", "mimeType": "text/markdown", "buffer": b"Annual leave allowance is 21 days per year. Ask your manager to approve leave."})
                owner.get_by_role("button", name="Upload and index").click()
                expect(owner.locator("#main").get_by_role("button", name="Leave handbook")).to_be_visible()
                owner.locator('[data-nav="chat"]').click()
                owner.get_by_role("textbox", name="Your question").fill("What is the annual leave allowance?")
                owner.get_by_role("button", name="Send question").click()
                expect(owner.locator(".message.assistant .message-text")).to_contain_text("21 days")
                owner.locator(".citation").first.click()
                expect(owner.locator("#dialog-body")).to_contain_text("21 days")
                owner.get_by_role("button", name="Close", exact=True).click()
                owner.locator('[data-nav="team"]').click()
                owner.get_by_role("button", name="Invite member").click()
                owner.get_by_label("Work email").fill("employee@browser.test")
                owner.get_by_role("button", name="Create invitation link").click()
                invite_url = owner.locator(".result-secret").inner_text()
                owner.get_by_role("button", name="Close", exact=True).click()
                employee_context = browser.new_context()
                employee = employee_context.new_page()
                employee.on("pageerror", lambda error: errors.append(str(error)))
                employee.goto(invite_url)
                employee.get_by_label("Your name").fill("Jordan Employee")
                employee.get_by_label("Work email").fill("employee@browser.test")
                employee.get_by_label("Password", exact=True).fill("browser-test-password-456")
                employee.get_by_role("button", name="Accept invitation").click()
                expect(employee.get_by_role("heading", name="Good to see you, Jordan.")).to_be_visible()
                expect(employee.locator('[data-nav="team"]')).to_have_count(0)
                employee.locator('[data-nav="workflows"]').click()
                employee.get_by_role("button", name="Start request").first.click()
                employee.get_by_label("Request title").fill("Design application access")
                employee.get_by_label("Details").fill("Need access to the design application for project work.")
                employee.get_by_role("button", name="Submit for approval").click()
                expect(employee.locator("#main")).to_contain_text("Waiting for a separate reviewer")
                expect(employee.get_by_role("button", name="Approve & create ticket", exact=True)).to_have_count(0)
                owner.locator('[data-nav="requests"]').click()
                owner.get_by_role("button", name="Approve & create ticket", exact=True).click()
                owner.get_by_label("Reviewer note").fill("Approved for the project")
                owner.get_by_role("button", name="Approve & create internal ticket", exact=True).click()
                expect(owner.locator("#main")).to_contain_text("executed")
                owner.get_by_role("button", name="Mark resolved").click()
                expect(owner.locator("#main")).to_contain_text("resolved")
                employee.locator('[data-nav="requests"]').click()
                expect(employee.locator("#main")).to_contain_text("resolved")
                owner.locator('[data-nav="automations"]').click()
                owner.get_by_role("button", name="New automation").click()
                owner.get_by_label("Name", exact=True).fill("Review old policies")
                owner.get_by_role("button", name="Create schedule").click()
                owner.get_by_role("button", name="Run due schedules").click()
                expect(owner.locator("#main")).to_contain_text("Created 0 internal follow-up task(s)")
                owner.locator('[data-nav="integrations"]').click()
                owner.get_by_label("Token name").fill("Browser test integration")
                owner.get_by_role("button", name="Generate token").click()
                expect(owner.locator("#new-token")).to_contain_text("av_")
                owner.get_by_role("button", name="Close", exact=True).click()
                owner.get_by_role("button", name="Revoke", exact=True).click()
                expect(owner.locator("#main")).to_contain_text("No active tokens")
                owner.locator('[data-nav="settings"]').click()
                owner.get_by_label("Assistant name").fill("Studio Guide")
                owner.get_by_role("button", name="Save changes").click()
                expect(owner.get_by_label("Assistant name")).to_have_value("Studio Guide")
                owner.locator('[data-nav="audit"]').click()
                expect(owner.locator("#main")).to_contain_text("action.approve")
                owner.locator('[data-nav="overview"]').click()
                artifacts = Path("artifacts/screenshots")
                artifacts.mkdir(parents=True, exist_ok=True)
                owner.screenshot(path=str(artifacts / "overview-desktop.png"), full_page=True)
                owner.set_viewport_size({"width": 390, "height": 844})
                expect(owner.locator(".nav")).to_be_visible()
                owner.screenshot(path=str(artifacts / "overview-mobile.png"), full_page=True)
                assert owner.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page overflows horizontally"
                browser.close()
                assert not errors, errors
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
    print("PASS: browser onboarding, ingestion, cited answer, source preview, invitation, employee request, separate approval, ticket resolution, automation, token creation/revocation, settings, audit and responsive layout")


if __name__ == "__main__":
    run()
