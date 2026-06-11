"""Authentication against Sotheby's (Auth0 + Cloudflare Turnstile).

Sotheby's login uses Cloudflare Turnstile, which reliably blocks automated
browsers (Playwright/Chromium). The supported flow is therefore **manual**:

  1. Open a real Chrome window (not headless).
  2. You log in yourself — email, captcha checkbox, password.
  3. The scraper listens for the bearer token on GraphQL requests and caches it.

You can also paste a token directly into .env as SOTHEBYS_BEARER_TOKEN
(copied from Chrome DevTools → Network → any graphql request → Authorization).
"""

from __future__ import annotations

import base64
import json
import logging
import time

from playwright.sync_api import Page, sync_playwright

from . import config

log = logging.getLogger(__name__)

BROWSER_PROFILE_DIR = config.PROJECT_ROOT / ".browser_profile"

LOGIN_ENTRY_URL = (
    "https://www.sothebys.com/api/auth0login?forceLogin=Y"
    "&resource=https%3A%2F%2Fwww.sothebys.com%2Fen%2F"
)

MANUAL_LOGIN_TIMEOUT_SECONDS = 300


def _jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0.0


def _load_cached_token() -> str | None:
    if config.SOTHEBYS_BEARER_TOKEN:
        log.info("Using bearer token from SOTHEBYS_BEARER_TOKEN in .env")
        return config.SOTHEBYS_BEARER_TOKEN

    if not config.TOKEN_CACHE_FILE.exists():
        return None
    try:
        cached = json.loads(config.TOKEN_CACHE_FILE.read_text())
        token = cached.get("access_token", "")
        if token and _jwt_exp(token) - time.time() > 300:
            log.info("Using cached bearer token from .token_cache.json")
            return token
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_cached_token(token: str) -> None:
    config.TOKEN_CACHE_FILE.write_text(json.dumps({"access_token": token}))


def _launch_browser(pw, headless: bool):
    """Launch real Chrome with automation flags stripped."""
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    }
    try:
        return pw.chromium.launch_persistent_context(channel="chrome", **kwargs)
    except Exception:
        log.warning("Could not launch system Chrome; falling back to bundled Chromium")
        return pw.chromium.launch_persistent_context(**kwargs)


def _extract_token_from_storage(page: Page) -> str | None:
    # localStorage is only accessible on www.sothebys.com, not on Auth0
    # or about:blank — reading it elsewhere throws a SecurityError.
    if "www.sothebys.com" not in page.url:
        return None
    try:
        token = page.evaluate(
            """() => {
                const read = (store) => {
                    for (let i = 0; i < store.length; i++) {
                        const raw = store.getItem(store.key(i));
                        if (!raw) continue;
                        try {
                            const parsed = JSON.parse(raw);
                            if (parsed?.body?.access_token) return parsed.body.access_token;
                            if (parsed?.access_token) return parsed.access_token;
                        } catch (_) {}
                        if (raw.split('.').length === 3 && raw.startsWith('ey')) return raw;
                    }
                    return null;
                };
                return read(localStorage) || read(sessionStorage);
            }"""
        )
        return token or None
    except Exception:
        return None


def _wait_for_token(page: Page, captured: dict[str, str], timeout_s: int) -> bool:
    """Poll until a bearer token is captured or timeout expires."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if captured.get("token"):
            return True
        storage = _extract_token_from_storage(page)
        if storage:
            captured["token"] = storage
            return True
        page.wait_for_timeout(1_000)
    return False


def _trigger_graphql(page: Page) -> None:
    """Navigate to pages that cause the SPA to fire authenticated GraphQL calls."""
    try:
        if "sothebys.com" not in page.url:
            return
        page.goto(f"{config.BASE_URL}/en/results", wait_until="domcontentloaded", timeout=60_000)
        link = page.query_selector("a[href*='/en/buy/auction/']")
        if link:
            href = link.get_attribute("href")
            if href:
                page.goto(href, wait_until="domcontentloaded", timeout=60_000)
    except Exception as exc:
        log.debug("Could not trigger GraphQL navigation: %s", exc)


def manual_login(timeout_seconds: int = MANUAL_LOGIN_TIMEOUT_SECONDS) -> str:
    """Open Chrome and wait for the user to log in manually.

    Steps shown in the terminal:
      1. A Chrome window opens on the Sotheby's login page.
      2. Enter your email and click Continue.
      3. Check the 'Verify you are human' box.
      4. Enter your password and submit.
      5. The scraper captures your session token automatically.
    """
    captured: dict[str, str] = {}

    print("\n" + "=" * 60)
    print("  MANUAL LOGIN REQUIRED")
    print("=" * 60)
    print("  A Chrome window will open. Please log in yourself:")
    print("    1. Enter your email  →  click Continue")
    print("    2. Check 'Verify you are human'")
    print("    3. Enter your password  →  click Continue")
    print(f"  Waiting up to {timeout_seconds // 60} minutes for you to finish ...")
    print("=" * 60 + "\n")

    with sync_playwright() as pw:
        context = _launch_browser(pw, headless=False)
        page = context.pages[0] if context.pages else context.new_page()

        def sniff_request(request) -> None:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer ") and "token" not in captured:
                captured["token"] = auth_header.split(" ", 1)[1]
                log.info("Bearer token captured from network request")

        page.on("request", sniff_request)

        # Check if a previous session is still valid.
        page.goto(
            f"{config.BASE_URL}/en/results",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        _trigger_graphql(page)
        if _wait_for_token(page, captured, timeout_s=5):
            context.close()
            _save_cached_token(captured["token"])
            log.info("Existing browser session is still valid")
            return captured["token"]

        # Fresh login — open the Auth0 page and let the user drive.
        page.goto(LOGIN_ENTRY_URL, wait_until="domcontentloaded", timeout=60_000)

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if captured.get("token"):
                break
            # Once the user lands back on sothebys.com, trigger GraphQL calls.
            if "www.sothebys.com" in page.url and "accounts.sothebys.com" not in page.url:
                _trigger_graphql(page)
            _wait_for_token(page, captured, timeout_s=2)

        context.close()

    token = captured.get("token")
    if not token:
        raise RuntimeError(
            "Login timed out — no bearer token was captured.\n\n"
            "Try one of these alternatives:\n"
            "  A) Run again and complete login in the Chrome window that opens.\n"
            "  B) Log in via your own Chrome, then copy the token:\n"
            "       DevTools (F12) → Network → filter 'graphql'\n"
            "       → click any request → Headers → Authorization\n"
            "       → paste the token (without 'Bearer ') into .env as:\n"
            "           SOTHEBYS_BEARER_TOKEN=<token>\n"
        )

    _save_cached_token(token)
    log.info("Login successful — token saved to .token_cache.json")
    return token


def login_and_get_token(headless: bool = False) -> str:
    """Return a valid bearer token, using cache/env first, then manual login."""
    cached = _load_cached_token()
    if cached:
        return cached

    if headless:
        log.warning(
            "Headless login is not supported — Turnstile blocks automated browsers. "
            "Switching to manual login."
        )

    return manual_login()
