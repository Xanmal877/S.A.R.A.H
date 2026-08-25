import logging
import os

logger = logging.getLogger("BrowserController")

PROFILE_DIR = os.path.expanduser("~/.sarah/browser_profile")

# Cheap, honest signal - not an attempt to beat these systems (see
# BrowserController's docstring), just to stop Sarah from burning reasoning
# cycles clicking around a challenge page as if it were normal content.
_BOT_CHECK_MARKERS = [
    "checking your browser", "just a moment", "attention required",
    "verify you are human", "unusual traffic", "captcha",
    "cf-turnstile", "datadome", "please verify you are a human",
]


class BrowserController:
    """
    Sarah's own browser, driven via Playwright (Firefox) rather than
    OS-level clicking (xdotool/X11) - CDP/Playwright automation works
    correctly on Wayland, where raw X11 window automation does not, and
    doesn't depend on window-manager/compositor quirks at all.

    Uses a dedicated, persistent profile (~/.sarah/browser_profile) that is
    separate from the operator's real browser - per the operator's explicit
    choice, this starts logged out of everything. It can only act on sites
    where the operator has deliberately logged in *within this profile*,
    not the operator's real day-to-day sessions/cookies.

    Launched lazily on first use and kept open across calls so navigation
    state persists between tool calls in the same conversation.
    """

    def __init__(self):
        self._playwright = None
        self._context = None
        self._page = None

    async def _ensure_started(self):
        if self._page is not None:
            return
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        os.makedirs(PROFILE_DIR, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.firefox.launch_persistent_context(
            PROFILE_DIR, headless=False
        )
        # Patches the common automation tells (navigator.webdriver, plugin
        # list, etc.) - helps against basic bot checks. Not a guarantee
        # against real anti-bot systems (Cloudflare/DataDome/Turnstile) -
        # see read_page()'s bot-check detection below for what to do when
        # she hits one of those instead of fighting it.
        await Stealth().apply_stealth_async(self._context)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        logger.info(f"Browser started (Firefox, profile={PROFILE_DIR}, stealth applied)")

    async def _bot_check_notice(self) -> str:
        try:
            title = (await self._page.title()).lower()
            body = (await self._page.inner_text("body"))[:500].lower()
        except Exception:
            return ""
        haystack = title + " " + body
        if any(marker in haystack for marker in _BOT_CHECK_MARKERS):
            return (
                " [BOT CHECK DETECTED: this page looks like an anti-bot challenge "
                "(Cloudflare/DataDome/captcha-style), not real content. Don't try to "
                "click through it or guess at solving it - report this to the user "
                "instead of continuing to act on this page.]"
            )
        return ""

    async def navigate(self, url: str) -> str:
        await self._ensure_started()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
        return f"Navigated to {self._page.url}{await self._bot_check_notice()}"

    async def click(self, text: str) -> str:
        """Clicks the first visible element matching `text` (link, button, etc.)."""
        await self._ensure_started()
        locator = self._page.get_by_text(text, exact=False).first
        await locator.click(timeout=10000)
        return f"Clicked element matching '{text}'"

    async def type_text(self, text: str, selector: str = None) -> str:
        """Types into the currently focused element, or into `selector` if given."""
        await self._ensure_started()
        if selector:
            await self._page.fill(selector, text, timeout=10000)
        else:
            await self._page.keyboard.type(text)
        return f"Typed text ({len(text)} chars)"

    async def read_page(self, max_chars: int = 3000) -> str:
        """Returns the visible text content of the current page."""
        await self._ensure_started()
        text = await self._page.inner_text("body")
        text = " ".join(text.split())
        return text[:max_chars]

    async def screenshot(self, path: str = None) -> str:
        await self._ensure_started()
        path = path or os.path.expanduser("~/.sarah/browser_screenshot.png")
        await self._page.screenshot(path=path)
        return f"Screenshot saved to {path}"

    async def close(self):
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._page = None
        self._playwright = None


browser = BrowserController()
