#!/usr/bin/env python3
"""Capture screenshots of the NeuronSphere Deployment GUI for the user guide.

This script drives a real browser through the flows documented in
``docs/user_guide/`` and saves PNGs into ``docs/images/`` using the exact
filenames the guide's ``.. figure::`` directives reference.

It is meant to be run *by you*, against a live environment, with your own
credentials. To avoid scripting SSO/MFA, the browser opens headed and waits for
you to log in manually the first time; the authenticated session is then saved
to ``docs/.auth.json`` (git-ignored) and reused on later runs.

Nothing destructive is done: the script creates a throwaway ChangeSet draft to
photograph the editor/review screens, but it never confirms an *Apply* (that
would trigger real deployments) — it only opens the Apply dialog to photograph
it.

Usage
-----
    pip install playwright
    playwright install chromium

    # Simplest — auto-discovers an environment and a repo class:
    python docs/capture_screenshots.py

    # Or pin the samples explicitly:
    python docs/capture_screenshots.py \
        --url https://app.hmdtr1-admin-neuronsphere.io \
        --environment admin \
        --repo-class hmd-ms-deployment

Environment variables (fallbacks for the CLI flags):
    NS_ADMIN_URL, NS_ENVIRONMENT, NS_REPO_CLASS
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from playwright.sync_api import (
        Page,
        TimeoutError as PWTimeout,
        sync_playwright,
    )
except ImportError:  # pragma: no cover - guidance only
    sys.exit(
        "Playwright is not installed. Run:\n"
        "    pip install playwright\n"
        "    playwright install chromium"
    )

DOCS_DIR = Path(__file__).resolve().parent
IMAGES_DIR = DOCS_DIR / "images"
AUTH_STATE = DOCS_DIR / ".auth.json"
DEFAULT_URL = "https://app.hmdtr1-admin-neuronsphere.io"

# Track what we managed to capture so we can report gaps at the end.
_written: list[str] = []
_skipped: list[tuple[str, str]] = []


def shot(page: Page, name: str, *, clip_selector: str | None = None) -> None:
    """Screenshot the page (or a single element) to docs/images/<name>."""
    path = IMAGES_DIR / name
    try:
        page.wait_for_timeout(400)  # let HTMX/Alpine settle
        if clip_selector:
            el = page.locator(clip_selector).first
            el.scroll_into_view_if_needed(timeout=3000)
            el.screenshot(path=str(path))
        else:
            page.screenshot(path=str(path), full_page=True)
        _written.append(name)
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001 - one bad screen shouldn't abort the run
        _skipped.append((name, str(exc).splitlines()[0]))
        print(f"  ✗ {name}  ({str(exc).splitlines()[0]})")


def logged_in(page: Page) -> bool:
    try:
        return page.get_by_role("link", name="Change Sets").is_visible(timeout=1500)
    except PWTimeout:
        return False


def ensure_login(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    if logged_in(page):
        print("Already authenticated (reused saved session).")
        return

    # We're on the login page — grab it before signing in.
    print("Login page detected — capturing it, then waiting for you to sign in…")
    shot(page, "login.png")
    print(
        "\n>>> Please log in in the browser window that just opened.\n"
        ">>> Complete any SSO / MFA prompts. Waiting up to 5 minutes…\n"
    )
    # Wait for the app shell to appear after the user authenticates.
    page.get_by_role("link", name="Change Sets").wait_for(timeout=300_000)
    print("Login detected. Continuing.")


def discover_environment(page: Page, base_url: str, given: str | None) -> str | None:
    if given:
        return given
    # Expand the Environments section and read the first env link (href /bom/<env>/).
    page.goto(base_url, wait_until="domcontentloaded")
    try:
        page.get_by_role("button", name="Environments").click()
        page.wait_for_timeout(300)
    except Exception:  # noqa: BLE001
        pass
    for a in page.locator("a[href*='/bom/']").all():
        href = a.get_attribute("href") or ""
        parts = [p for p in href.split("/bom/", 1)[-1].split("/") if p]
        if parts:
            return parts[0]
    return None


def discover_repo_class(page: Page, base_url: str, given: str | None) -> str | None:
    if given:
        return given
    page.goto(f"{base_url}/repo-classes/", wait_until="domcontentloaded")
    link = page.locator("table tbody tr td a").first
    try:
        return (link.text_content() or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def capture_sidebar(page: Page, base_url: str) -> None:
    print("Navigation…")
    page.goto(base_url, wait_until="domcontentloaded")
    try:
        page.get_by_role("button", name="Environments").click()
        page.wait_for_timeout(300)
    except Exception:  # noqa: BLE001
        pass
    shot(page, "sidebar_nav.png", clip_selector="aside")


def capture_bom(page: Page, base_url: str, env: str) -> None:
    print(f"Environment BOM ({env})…")
    page.goto(f"{base_url}/bom/{env}/", wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    shot(page, "bom_table.png")
    shot(page, "bom_filters.png", clip_selector="form")

    # Instance detail slide-over: click the first instance in the table.
    try:
        page.locator("#bom-table a, #bom-table button").first.click(timeout=4000)
        page.locator("#instance-panel").wait_for(state="visible", timeout=4000)
        page.wait_for_timeout(600)
        shot(page, "instance_detail_panel.png")
        page.keyboard.press("Escape")
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("instance_detail_panel.png", str(exc).splitlines()[0]))
        print(f"  ✗ instance_detail_panel.png  ({str(exc).splitlines()[0]})")

    # DAG view.
    try:
        page.get_by_role("button", name="DAG View").click()
        page.wait_for_timeout(1500)
        shot(page, "bom_dag.png")
        page.get_by_role("button", name="Table View").click()
        page.wait_for_timeout(500)
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("bom_dag.png", str(exc).splitlines()[0]))
        print(f"  ✗ bom_dag.png  ({str(exc).splitlines()[0]})")

    # Selecting instances + naming a ChangeSet (only if the user can deploy).
    try:
        page.locator("#bom-table input[type=checkbox]").first.check(timeout=3000)
        page.locator("input[name=name]").first.fill("demo-changeset")
        page.wait_for_timeout(300)
        shot(page, "bom_select_create_changeset.png")
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("bom_select_create_changeset.png", str(exc).splitlines()[0]))
        print(f"  ✗ bom_select_create_changeset.png  ({str(exc).splitlines()[0]})")


def capture_changeset(page: Page, base_url: str, repo_class: str | None) -> str | None:
    print("ChangeSet creation…")
    page.goto(f"{base_url}/changeset/new/", wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    shot(page, "changeset_create_form.png")

    # Create a throwaway draft so we can photograph the editor + review screens.
    draft_url = None
    try:
        page.locator("input[name=name]").fill("guide-screenshots-demo")
        page.get_by_role("button", name="Create ChangeSet").click()
        page.wait_for_url("**/changeset/*/", timeout=8000)
        draft_url = page.url
        page.wait_for_timeout(800)
        shot(page, "changeset_draft_add_instance.png")
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("changeset_draft_add_instance.png", str(exc).splitlines()[0]))
        print(f"  ✗ could not create draft  ({str(exc).splitlines()[0]})")
        return None

    # Fill the Add Instance form far enough to load the dependency picker.
    try:
        page.locator("input[name=instance_name]").fill("demo-instance")
        if repo_class:
            page.locator("#repo_class_input").select_option(label=repo_class)
        else:
            page.locator("#repo_class_input").select_option(index=1)
        page.wait_for_timeout(1200)  # versions load via HTMX
        page.locator("#version_input").select_option(index=1)
        page.wait_for_timeout(1200)  # dependency picker loads via HTMX
        shot(page, "dependency_picker.png", clip_selector="form")

        # Add the instance and photograph the resulting Changes list.
        page.get_by_role("button", name="Add to ChangeSet").click()
        page.wait_for_timeout(1000)
        shot(page, "changeset_items_list.png", clip_selector="#changeset-items")

        # Inline instance editor.
        page.get_by_role("button", name="Edit instance").first.click()
        page.wait_for_timeout(1000)
        shot(page, "instance_editor_inline.png", clip_selector="#changeset-items")

        # Inline dependency editor.
        page.get_by_role("button", name="Edit dependencies").first.click()
        page.wait_for_timeout(1000)
        shot(page, "edit_dependencies.png", clip_selector="#changeset-items")
    except Exception as exc:  # noqa: BLE001
        line = str(exc).splitlines()[0]
        for n in ("dependency_picker.png", "changeset_items_list.png",
                  "instance_editor_inline.png", "edit_dependencies.png"):
            if n not in _written and all(n != s[0] for s in _skipped):
                _skipped.append((n, line))
        print(f"  ✗ add/edit instance flow incomplete  ({line})")

    return draft_url


def capture_review(page: Page, draft_url: str, env: str) -> None:
    print("ChangeSet review + apply…")
    review_url = draft_url.rstrip("/") + "/review/"
    page.goto(review_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)  # validation runs on load
    shot(page, "changeset_review.png")

    # BOM impact preview.
    try:
        page.locator("input[name=impact_environment]").fill(env)
        page.get_by_role("button", name="Preview").click()
        page.wait_for_timeout(1500)
        shot(page, "bom_impact_preview.png")
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("bom_impact_preview.png", str(exc).splitlines()[0]))
        print(f"  ✗ bom_impact_preview.png  ({str(exc).splitlines()[0]})")

    # Apply dialog — open ONLY, never submit (submitting triggers deployments).
    try:
        page.get_by_role("button", name="Apply to DeploymentSet").click()
        page.wait_for_timeout(600)
        shot(page, "apply_modal.png")
        page.get_by_role("button", name="Cancel").first.click()
        page.wait_for_timeout(300)
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("apply_modal.png", str(exc).splitlines()[0]))
        print(f"  ✗ apply_modal.png  ({str(exc).splitlines()[0]})")

    # Reject dialog.
    try:
        page.get_by_role("button", name="Reject").click()
        page.wait_for_timeout(600)
        shot(page, "changeset_reject_modal.png")
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("changeset_reject_modal.png", str(exc).splitlines()[0]))
        print(f"  ✗ changeset_reject_modal.png  ({str(exc).splitlines()[0]})")


def capture_repo_classes(page: Page, base_url: str, repo_class: str | None) -> None:
    print("Repo classes…")
    page.goto(f"{base_url}/repo-classes/", wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    shot(page, "repo_class_list.png")

    target = f"{base_url}/repo-classes/{repo_class}/" if repo_class else None
    try:
        if target:
            page.goto(target, wait_until="domcontentloaded")
        else:
            page.locator("table tbody tr td a").first.click()
        page.wait_for_timeout(600)
        # Expand the first "Show" default-configuration disclosure if present.
        try:
            page.get_by_text("Show", exact=True).first.click(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:  # noqa: BLE001
            pass
        shot(page, "repo_class_versions.png")
    except Exception as exc:  # noqa: BLE001
        _skipped.append(("repo_class_versions.png", str(exc).splitlines()[0]))
        print(f"  ✗ repo_class_versions.png  ({str(exc).splitlines()[0]})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("NS_ADMIN_URL", DEFAULT_URL))
    parser.add_argument("--environment", default=os.environ.get("NS_ENVIRONMENT"))
    parser.add_argument("--repo-class", default=os.environ.get("NS_REPO_CLASS"))
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            storage_state=str(AUTH_STATE) if AUTH_STATE.exists() else None,
        )
        page = context.new_page()

        ensure_login(page, base_url)
        context.storage_state(path=str(AUTH_STATE))  # persist session for next run

        env = discover_environment(page, base_url, args.environment)
        repo_class = discover_repo_class(page, base_url, args.repo_class)
        print(f"Using environment={env!r}, repo_class={repo_class!r}\n")

        capture_sidebar(page, base_url)
        if env:
            capture_bom(page, base_url, env)
        else:
            print("No accessible environment found — skipping BOM screenshots.")

        draft_url = capture_changeset(page, base_url, repo_class)
        if draft_url and env:
            capture_review(page, draft_url, env)
        capture_repo_classes(page, base_url, repo_class)

        context.storage_state(path=str(AUTH_STATE))
        browser.close()

    print("\n=== Summary ===")
    print(f"Captured {len(_written)} screenshot(s) into {IMAGES_DIR}")
    if _skipped:
        print(f"Skipped {len(_skipped)}:")
        for name, reason in _skipped:
            print(f"  - {name}: {reason}")
        print(
            "\nSkipped screens usually mean the sample environment/repo-class had "
            "no matching data, or you lack deploy permission. Re-run with "
            "--environment / --repo-class pointing at data you can see."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
