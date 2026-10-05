"""
Autonomous reflection scheduler: coordinates perception capture (screen watching)
and reflection (reasoning) on separate intervals, with background task management
and duplicate suppression.

Key behaviors:
- Perception: first immediately, then on 1s interval
- Reflection: first immediately, then on 60s interval (default)
- At most one reflection task in flight; new checks do not cancel active tasks
- Exact-text suggestion cache with bounded size
- Optional monotonic clock injection for testing
- Safe shutdown handling
"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("ReflectionScheduler")


class ReflectionScheduler:
    """Coordinates perception and reflection intervals with injectible clock and
    background task management.
    
    Perception (screen watching):
    - First immediately
    - Then at 1s intervals
    
    Reflection (reasoning loop):
    - First immediately
    - Then at configured interval (default 60s)
    - At most one task in flight (new calls do not cancel active tasks)
    - Optional timeout for wrapped operations
    
    Suggestion cache:
    - Bounded exact-text deduplication
    - Evicts oldest on overflow
    """
    
    def __init__(
        self,
        perception_fn: Callable[[], Awaitable[None]],
        reflection_fn: Callable[[], Awaitable[None]],
        perception_interval_s: float = 1.0,
        reflection_interval_s: float = 60.0,
        suggestion_cache_size: int = 50,
        clock_fn: Optional[Callable[[], float]] = None,
    ):
        """
        Args:
            perception_fn: async callable for screen capture/perception
            reflection_fn: async callable for reasoning/reflection
            perception_interval_s: interval between perception calls (default 1s)
            reflection_interval_s: interval between reflection calls (default 60s)
            suggestion_cache_size: max size of exact-text suggestion dedup (default 50)
            clock_fn: optional monotonic time function (defaults to time.monotonic)
        """
        self.perception_fn = perception_fn
        self.reflection_fn = reflection_fn
        self.perception_interval_s = perception_interval_s
        self.reflection_interval_s = reflection_interval_s
        self.suggestion_cache_size = suggestion_cache_size
        self.clock_fn = clock_fn or time.monotonic
        
        # Timing state
        self._perception_last_s = -float('inf')
        self._reflection_last_s = -float('inf')
        
        # In-flight reflection task
        self._reflection_task: Optional[asyncio.Task] = None
        
        # Suggestion cache: set of recently seen text suggestions
        self._suggestion_cache: list = []  # ordered, for FIFO eviction
        
        # Shutdown flag
        self._shutdown = False
        
        # Diagnostics counters
        self._perception_calls = 0
        self._reflection_calls = 0
        self._reflection_skipped_in_flight = 0
        self._cache_evictions = 0
    
    # ===== Clock
    
    def _now(self) -> float:
        """Current monotonic time."""
        return self.clock_fn()
    
    # ===== Interval gating
    
    def should_perceive(self) -> bool:
        """Check if it's time to perceive (interval gate)."""
        now = self._now()
        return (now - self._perception_last_s) >= self.perception_interval_s
    
    def should_reflect(self) -> bool:
        """Check if it's time to reflect and no task is in flight."""
        if self._reflection_task is not None and not self._reflection_task.done():
            self._reflection_skipped_in_flight += 1
            return False
        now = self._now()
        return (now - self._reflection_last_s) >= self.reflection_interval_s
    
    # ===== Suggestion cache
    
    def is_duplicate_suggestion(self, text: str) -> bool:
        """Check if this exact text is in the cache."""
        return text in self._suggestion_cache
    
    def record_suggestion(self, text: str) -> None:
        """Add text to cache, evicting oldest if full."""
        if text in self._suggestion_cache:
            return
        self._suggestion_cache.append(text)
        if len(self._suggestion_cache) > self.suggestion_cache_size:
            self._suggestion_cache.pop(0)
            self._cache_evictions += 1
    
    def clear_cache(self) -> None:
        """Clear the suggestion cache."""
        self._suggestion_cache.clear()
    
    # ===== Perception
    
    async def maybe_perceive(self) -> bool:
        """Invoke perception if interval gate permits. Returns True if called.
        Safe to call every tick; returns False if gated."""
        if not self.should_perceive():
            return False
        
        self._perception_last_s = self._now()
        self._perception_calls += 1
        
        try:
            await self.perception_fn()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Perception error: {e}")
        
        return True
    
    # ===== Reflection
    
    async def maybe_reflect(self) -> bool:
        """Invoke reflection if interval gate and no task in flight. Returns True if called.
        Safe to call every tick; returns False if gated or task is in flight."""
        if not self.should_reflect():
            return False
        
        self._reflection_last_s = self._now()
        self._reflection_calls += 1
        
        # Launch in background; do not await. The wrapper consumes exceptions
        # so a scheduler-owned callback can never leave an unhandled Task
        # exception behind if a caller forgets to catch one itself.
        self._reflection_task = asyncio.create_task(self._run_reflection())
        return True

    async def _run_reflection(self) -> None:
        try:
            await self.reflection_fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reflection error")
    
    # ===== Diagnostics
    
    def get_diagnostics(self) -> dict:
        """Return scheduler diagnostics."""
        now = self._now()
        return {
            "perception_calls": self._perception_calls,
            "reflection_calls": self._reflection_calls,
            "reflection_skipped_in_flight": self._reflection_skipped_in_flight,
            "cache_evictions": self._cache_evictions,
            "cache_size": len(self._suggestion_cache),
            "perception_seconds_since_last": now - self._perception_last_s,
            "reflection_seconds_since_last": now - self._reflection_last_s,
            "reflection_task_in_flight": self._reflection_task is not None and not self._reflection_task.done(),
        }
    
    # ===== Shutdown
    
    async def shutdown(self) -> None:
        """Safely shut down: await any in-flight reflection task."""
        self._shutdown = True
        if self._reflection_task is not None and not self._reflection_task.done():
            try:
                await self._reflection_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"Reflection task exception during shutdown: {e}")
