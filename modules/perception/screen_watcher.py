import asyncio
import base64
import difflib
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Optional

logger = logging.getLogger("ScreenWatcher")

# Deliberately asks for a *description*, not a transcription. The local
# vision model is the only thing that ever sees the raw screenshot; this
# text is the sole output allowed to leave that boundary (see
# LLMClient.describe_image / LLMClient.is_local).
REDACTION_PROMPT = (
    "You are looking at a screenshot of a personal computer desktop. In a few sentences, "
    "describe what is generally happening on screen - which kinds of apps/windows are open, "
    "the general nature of the content, and what the user appears to be doing - so another "
    "AI system can react to the context.\n\n"
    "IMPORTANT: Do not transcribe or repeat any specific sensitive data visible on screen, "
    "even partially. Never include: passwords, API keys/tokens, seed phrases, credit card or "
    "bank account numbers, the literal contents of private messages/emails, or personal "
    "identifying information (full names, addresses, phone numbers, email addresses). Describe "
    "the *category* of such content instead (e.g. \"a password entry field\", \"a private chat "
    "conversation\", \"a code editor with a config file\") without quoting the actual text. "
    "Be a general observer, not a transcriber."
)


class ScreenWatcher:
    """
    Gives Sarah continuous, lightweight visual awareness: periodically
    captures the full screen and has a local vision model describe (and
    redact) it, on its own cadence (default every 7s, independent of the
    1s agent tick), so ObservationModule can fold what's on-screen into
    her world state.

    Capture runs an ordered chain of screenshot tools and takes the first
    one that produces a PNG (see CAPTURE_CHAIN). No single tool is assumed
    to exist: `spectacle` is KDE's, `grim` is Wayland-native, and `mss` is a
    pure-Python fallback that works over XWayland. The screenshot image
    itself is only ever handed to `vision_client`, which must be local
    (LLMClient.is_local) - `describe_image` refuses otherwise. Only the
    resulting sanitized text description is kept/exposed further, e.g. to
    a cloud reasoning engine.
    """

    # (program, argv-template) in priority order. {out} is the output file.
    # Adding a capture backend is a one-line change here - never logic.
    CAPTURE_CHAIN = (
        ("spectacle", ("spectacle", "-b", "-n", "-f", "-o", "{out}")),
        ("grim", ("grim", "{out}")),
        ("gnome-screenshot", ("gnome-screenshot", "-f", "{out}")),
    )

    def __init__(self, vision_client, interval: float = 7.0, clock_fn: Optional[Callable[[], float]] = None):
        if not vision_client.is_local:
            raise ValueError(
                "ScreenWatcher requires a local vision_client - raw screen "
                "images must never be sent to a non-local reasoning engine."
            )
        self.vision_client = vision_client
        self.interval = interval
        self.clock_fn = clock_fn or time.monotonic
        self.last_capture_time = 0.0
        self.last_text = ""
        self.last_changed = False
        # Which backend last succeeded / how it last failed. Diagnostic only,
        # but it is what makes a blind start *visible* instead of silent - the
        # failure mode that hid "spectacle SIGABRT" for weeks.
        self.last_backend = None
        self._capture_failures_logged = False
        self._log_session_env()

    @staticmethod
    def _log_session_env():
        """Log the graphical-session variables this process actually has.

        A screenshot tool can only work if the daemon inherited the desktop
        session's environment (WAYLAND_DISPLAY / XDG_RUNTIME_DIR / DISPLAY).
        Logging them once at startup turns 'she is blind' into either an
        explicit misconfiguration or a genuine capture-tool failure.
        """
        env = {k: os.environ.get(k, "<unset>") for k in
               ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY",
                "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")}
        logger.info("Screen capture session env: " +
                    ", ".join(f"{k}={v}" for k, v in env.items()))

    def _capture_and_encode_sync(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            shot_path = os.path.join(tmpdir, "screen.png")
            errors = []
            for program, argv in self.CAPTURE_CHAIN:
                if shutil.which(program) is None:
                    continue
                out_arg = argv[-1].format(out=shot_path)
                run_argv = [out_arg if a == "{out}" else a for a in argv]
                try:
                    subprocess.run(
                        run_argv, timeout=15, check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                        OSError) as e:
                    errors.append(f"{program}: {e}")
                    continue
                if not os.path.exists(shot_path):
                    errors.append(f"{program}: produced no file")
                    continue
                try:
                    with open(shot_path, "rb") as f:
                        data = f.read()
                except OSError as e:
                    errors.append(f"{program}: {e}")
                    continue
                if not data:
                    errors.append(f"{program}: empty file")
                    continue
                self.last_backend = program
                self._capture_failures_logged = False
                return base64.b64encode(data).decode()

            if errors and not self._capture_failures_logged:
                # Log verbosely once, then stay quiet until a success, so a
                # broken capture path is loud but does not spam every 7s.
                logger.warning("All screen capture backends failed: " + "; ".join(errors))
                self._capture_failures_logged = True
            return ""

    async def maybe_capture(self) -> bool:
        """Capture + describe on the configured interval. Returns True if
        a new description was obtained this call."""
        now = self.clock_fn()
        if now - self.last_capture_time < self.interval:
            return False
        self.last_capture_time = now

        image_b64 = await asyncio.to_thread(self._capture_and_encode_sync)
        if not image_b64:
            return False

        description = await self.vision_client.describe_image(image_b64, REDACTION_PROMPT)
        if description.startswith("Error:"):
            logger.warning(f"Vision description failed: {description}")
            return False

        self.last_changed = self._is_significant_change(self.last_text, description)
        self.last_text = description
        return True

    @staticmethod
    def _is_significant_change(old: str, new: str, threshold: float = 0.35) -> bool:
        if not old and new:
            return True
        if not new:
            return False
        ratio = difflib.SequenceMatcher(None, old, new).ratio()
        return (1.0 - ratio) >= threshold

    def get_summary(self) -> str:
        if not self.last_text:
            return "No screen description captured yet."
        changed_note = " (changed since last look)" if self.last_changed else " (largely unchanged)"
        return f"{self.last_text}{changed_note}"
