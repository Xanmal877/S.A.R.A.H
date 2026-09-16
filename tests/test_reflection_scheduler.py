"""
Unit tests for the ReflectionScheduler module.

Tests cover:
- Interval gating (perception at 1s, reflection at 60s)
- In-flight task gating (no concurrent reflection tasks)
- Suggestion cache deduplication and eviction
- Timeout handling
- Scheduler shutdown and cleanup
- Clock injection for deterministic testing
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, call

from modules.reflection.scheduler import ReflectionScheduler


class MockClock:
    """Injectable clock for deterministic time-based testing."""
    def __init__(self):
        self.time = 0.0
    
    def __call__(self):
        return self.time
    
    def advance(self, delta: float):
        """Advance time by delta seconds."""
        self.time += delta


class IntervalGatTests(unittest.TestCase):
    """Test interval gating behavior - focus on gate logic, not execution."""
    
    def setUp(self):
        self.clock = MockClock()
        self.perception_calls = []
        
        async def perception_fn():
            self.perception_calls.append(self.clock.time)
        
        async def reflection_fn():
            pass  # Don't care about execution, just gating
        
        self.scheduler = ReflectionScheduler(
            perception_fn=perception_fn,
            reflection_fn=reflection_fn,
            perception_interval_s=1.0,
            reflection_interval_s=60.0,
            clock_fn=self.clock,
        )
    
    def test_first_perception_is_immediate(self):
        """First perception should be called immediately (interval is -inf)."""
        async def run():
            result = await self.scheduler.maybe_perceive()
            self.assertTrue(result)
        
        asyncio.run(run())
        self.assertEqual(len(self.perception_calls), 1)
        self.assertEqual(self.perception_calls[0], 0.0)
    
    def test_first_reflection_is_immediate(self):
        """First reflection should be called immediately (interval is -inf)."""
        async def run():
            result = await self.scheduler.maybe_reflect()
            self.assertTrue(result)
        
        asyncio.run(run())
    
    def test_perception_gated_before_interval(self):
        """Perception should be gated before 1s interval elapses."""
        async def run():
            result = await self.scheduler.maybe_perceive()
            self.assertTrue(result)
            self.perception_calls.clear()
            
            # Advance to 0.5s - should NOT call
            self.clock.advance(0.5)
            result = await self.scheduler.maybe_perceive()
            self.assertFalse(result)
            self.assertEqual(len(self.perception_calls), 0)
            
            # Advance to 1.0s total - SHOULD call
            self.clock.advance(0.5)
            result = await self.scheduler.maybe_perceive()
            self.assertTrue(result)
            self.assertEqual(len(self.perception_calls), 1)
        
        asyncio.run(run())
    
    def test_reflection_gated_before_interval(self):
        """Reflection should be gated before 60s interval elapses."""
        async def run():
            result = await self.scheduler.maybe_reflect()
            self.assertTrue(result)
            
            # Advance to 30s - should NOT call (gated by interval)
            self.clock.advance(30.0)
            result = await self.scheduler.maybe_reflect()
            self.assertFalse(result)  # Gated by in-flight task or interval
            
            # Wait for first task to complete
            await asyncio.sleep(0.01)
            
            # Advance to 60s total - SHOULD call
            self.clock.advance(30.0)
            result = await self.scheduler.maybe_reflect()
            self.assertTrue(result)  # Called
        
        asyncio.run(run())
    
    def test_should_perceive_gate_logic(self):
        """Test the should_perceive gate logic directly."""
        # First check returns True (initial state has -inf)
        self.assertTrue(self.scheduler.should_perceive())
        
        # Simulate a call that updates the timestamp
        async def run():
            await self.scheduler.maybe_perceive()
            # Now timestamp is set to 0.0
            self.clock.advance(0.5)
            self.assertFalse(self.scheduler.should_perceive())
            self.clock.advance(0.6)
            self.assertTrue(self.scheduler.should_perceive())
        
        asyncio.run(run())
    
    def test_should_reflect_gate_logic(self):
        """Test the should_reflect gate logic directly (ignoring in-flight check for now)."""
        # First check returns True (initial state has -inf)
        self.assertTrue(self.scheduler.should_reflect())
        
        # Simulate a call that updates the timestamp and check interval gate
        async def run():
            await self.scheduler.maybe_reflect()
            # Now timestamp is set to 0.0
            
            # Wait for task to complete so in-flight check passes
            await asyncio.sleep(0.01)
            
            # At 30s, interval gate should fail (not 60s yet)
            self.clock.advance(30.0)
            self.assertFalse(self.scheduler.should_reflect())
            
            # At 60s, interval gate should pass
            self.clock.advance(30.0)
            self.assertTrue(self.scheduler.should_reflect())
        
        asyncio.run(run())


class InFlightTaskGatingTests(unittest.TestCase):
    """Test in-flight reflection task gating."""
    
    def setUp(self):
        self.clock = MockClock()
    
    def test_no_concurrent_reflection_tasks(self):
        """New reflection calls should not launch while a task is in flight."""
        task_count = []
        task_started = asyncio.Event()
        
        async def reflection_fn():
            task_count.append(1)
            task_started.set()
            await asyncio.sleep(10.0)  # Long sleep to keep task in flight
        
        scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=reflection_fn,
            reflection_interval_s=1.0,
            clock_fn=self.clock,
        )
        
        async def run():
            # Launch first reflection
            result = await scheduler.maybe_reflect()
            self.assertTrue(result)
            
            # Wait for task to start
            await asyncio.wait_for(task_started.wait(), timeout=1.0)
            self.assertEqual(len(task_count), 1)
            
            # Try again immediately - should be gated (task in flight)
            result = await scheduler.maybe_reflect()
            self.assertFalse(result)
            self.assertEqual(len(task_count), 1)
            
            # Advance time past interval, task still in flight
            self.clock.advance(2.0)
            result = await scheduler.maybe_reflect()
            self.assertFalse(result)
            self.assertEqual(len(task_count), 1)
        
        asyncio.run(run())
    
    def test_reflection_skipped_counter(self):
        """Scheduler should count checks rejected due to in-flight tasks."""
        async def reflection_fn():
            await asyncio.sleep(10.0)
        
        scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=reflection_fn,
            reflection_interval_s=1.0,
            clock_fn=self.clock,
        )
        
        async def run():
            result = await scheduler.maybe_reflect()
            self.assertTrue(result)
            
            # Try while task is in flight (interval has elapsed)
            self.clock.advance(1.1)
            initial_skips = scheduler._reflection_skipped_in_flight
            result = await scheduler.maybe_reflect()
            self.assertFalse(result)
            self.assertEqual(scheduler._reflection_skipped_in_flight, initial_skips + 1)
            
            # Try again while task is still in flight
            result = await scheduler.maybe_reflect()
            self.assertFalse(result)
            self.assertEqual(scheduler._reflection_skipped_in_flight, initial_skips + 2)
        
        asyncio.run(run())


class SuggestionCacheTests(unittest.TestCase):
    """Test suggestion deduplication cache."""
    
    def setUp(self):
        self.scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=AsyncMock(),
            suggestion_cache_size=3,
        )
    
    def test_cache_stores_suggestions(self):
        """Cache should store exact text suggestions."""
        self.assertFalse(self.scheduler.is_duplicate_suggestion("hello"))
        self.scheduler.record_suggestion("hello")
        self.assertTrue(self.scheduler.is_duplicate_suggestion("hello"))
    
    def test_cache_differentiates_text(self):
        """Cache should distinguish different texts."""
        self.scheduler.record_suggestion("hello")
        self.assertTrue(self.scheduler.is_duplicate_suggestion("hello"))
        self.assertFalse(self.scheduler.is_duplicate_suggestion("hello world"))
    
    def test_cache_evicts_oldest_on_overflow(self):
        """Cache should evict oldest entry when exceeding size limit."""
        self.scheduler.record_suggestion("first")
        self.scheduler.record_suggestion("second")
        self.scheduler.record_suggestion("third")
        self.assertEqual(len(self.scheduler._suggestion_cache), 3)
        
        # Add one more - should evict "first"
        self.scheduler.record_suggestion("fourth")
        self.assertEqual(len(self.scheduler._suggestion_cache), 3)
        self.assertFalse(self.scheduler.is_duplicate_suggestion("first"))
        self.assertTrue(self.scheduler.is_duplicate_suggestion("second"))
        self.assertTrue(self.scheduler.is_duplicate_suggestion("third"))
        self.assertTrue(self.scheduler.is_duplicate_suggestion("fourth"))
    
    def test_eviction_counter(self):
        """Scheduler should count cache evictions."""
        self.scheduler.record_suggestion("a")
        self.scheduler.record_suggestion("b")
        self.scheduler.record_suggestion("c")
        self.assertEqual(self.scheduler._cache_evictions, 0)
        
        self.scheduler.record_suggestion("d")
        self.assertEqual(self.scheduler._cache_evictions, 1)
        
        self.scheduler.record_suggestion("e")
        self.assertEqual(self.scheduler._cache_evictions, 2)
    
    def test_duplicate_not_re_recorded(self):
        """Adding duplicate to cache should not re-record or trigger eviction."""
        self.scheduler.record_suggestion("hello")
        self.assertEqual(len(self.scheduler._suggestion_cache), 1)
        
        self.scheduler.record_suggestion("hello")
        self.assertEqual(len(self.scheduler._suggestion_cache), 1)
        self.assertEqual(self.scheduler._cache_evictions, 0)
    
    def test_cache_clear(self):
        """Cache should be clearable."""
        self.scheduler.record_suggestion("a")
        self.scheduler.record_suggestion("b")
        self.assertEqual(len(self.scheduler._suggestion_cache), 2)
        
        self.scheduler.clear_cache()
        self.assertEqual(len(self.scheduler._suggestion_cache), 0)
        self.assertFalse(self.scheduler.is_duplicate_suggestion("a"))


class TimeoutHandlingTests(unittest.TestCase):
    """Test timeout wrapping and handling."""
    
    def setUp(self):
        self.clock = MockClock()
    
    def test_perception_exception_logged_not_raised(self):
        """Perception exceptions should be logged but not crash the scheduler."""
        async def failing_perception():
            raise ValueError("Perception failed!")
        
        scheduler = ReflectionScheduler(
            perception_fn=failing_perception,
            reflection_fn=AsyncMock(),
            clock_fn=self.clock,
        )
        
        async def run():
            # Should not raise
            result = await scheduler.maybe_perceive()
            self.assertTrue(result)  # Was called
        
        asyncio.run(run())
    
    def test_reflection_exception_logged_not_raised(self):
        """Reflection exceptions should be logged but not crash the scheduler."""
        async def failing_reflection():
            raise RuntimeError("Reflection failed!")
        
        scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=failing_reflection,
            clock_fn=self.clock,
        )
        
        async def run():
            # Should not raise
            result = await scheduler.maybe_reflect()
            self.assertTrue(result)  # Was called
            await asyncio.sleep(0.1)  # Let task run
        
        asyncio.run(run())


class DiagnosticsTests(unittest.TestCase):
    """Test scheduler diagnostics."""
    
    def setUp(self):
        self.clock = MockClock()
        self.scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=AsyncMock(),
            perception_interval_s=1.0,
            reflection_interval_s=60.0,
            clock_fn=self.clock,
        )
    
    def test_diagnostics_structure(self):
        """Diagnostics should contain expected fields."""
        async def run():
            await self.scheduler.maybe_perceive()
            diag = self.scheduler.get_diagnostics()
            
            self.assertIn("perception_calls", diag)
            self.assertIn("reflection_calls", diag)
            self.assertIn("reflection_skipped_in_flight", diag)
            self.assertIn("cache_evictions", diag)
            self.assertIn("cache_size", diag)
            self.assertIn("perception_seconds_since_last", diag)
            self.assertIn("reflection_seconds_since_last", diag)
            self.assertIn("reflection_task_in_flight", diag)
        
        asyncio.run(run())
    
    def test_diagnostics_counters(self):
        """Diagnostics should report accurate counters."""
        async def run():
            await self.scheduler.maybe_perceive()
            await self.scheduler.maybe_reflect()
            
            diag = self.scheduler.get_diagnostics()
            self.assertEqual(diag["perception_calls"], 1)
            self.assertEqual(diag["reflection_calls"], 1)
        
        asyncio.run(run())
    
    def test_diagnostics_timing(self):
        """Diagnostics should report accurate timing info."""
        async def run():
            await self.scheduler.maybe_perceive()
            self.assertEqual(self.scheduler.get_diagnostics()["perception_seconds_since_last"], 0.0)
            
            self.clock.advance(0.5)
            self.assertEqual(self.scheduler.get_diagnostics()["perception_seconds_since_last"], 0.5)
            
            self.clock.advance(0.5)
            self.assertEqual(self.scheduler.get_diagnostics()["perception_seconds_since_last"], 1.0)
        
        asyncio.run(run())


class ShutdownTests(unittest.TestCase):
    """Test safe shutdown behavior."""
    
    def test_shutdown_awaits_in_flight_task(self):
        """Shutdown should await any in-flight reflection task."""
        task_completed = []
        
        async def slow_reflection():
            await asyncio.sleep(0.1)
            task_completed.append(True)
        
        clock = MockClock()
        scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=slow_reflection,
            clock_fn=clock,
        )
        
        async def run():
            # Start a reflection task
            await scheduler.maybe_reflect()
            
            # Shut down - should wait for task to complete
            await scheduler.shutdown()
            
            # Task should have completed
            self.assertEqual(len(task_completed), 1)
        
        asyncio.run(run())
    
    def test_shutdown_with_no_task(self):
        """Shutdown should be safe when no reflection task is in flight."""
        async def run():
            scheduler = ReflectionScheduler(
                perception_fn=AsyncMock(),
                reflection_fn=AsyncMock(),
            )
            # No task started
            await scheduler.shutdown()  # Should not raise
        
        asyncio.run(run())
    
    def test_shutdown_sets_flag(self):
        """Shutdown should set the _shutdown flag."""
        async def run():
            scheduler = ReflectionScheduler(
                perception_fn=AsyncMock(),
                reflection_fn=AsyncMock(),
            )
            self.assertFalse(scheduler._shutdown)
            await scheduler.shutdown()
            self.assertTrue(scheduler._shutdown)
        
        asyncio.run(run())


class ReturnValueTests(unittest.TestCase):
    """Test return values from maybe_perceive and maybe_reflect."""
    
    def setUp(self):
        self.clock = MockClock()
        self.scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=AsyncMock(),
            perception_interval_s=1.0,
            reflection_interval_s=60.0,
            clock_fn=self.clock,
        )
    
    def test_maybe_perceive_returns_true_when_called(self):
        """maybe_perceive should return True when actually called."""
        async def run():
            result = await self.scheduler.maybe_perceive()
            self.assertTrue(result)
        
        asyncio.run(run())
    
    def test_maybe_perceive_returns_false_when_gated(self):
        """maybe_perceive should return False when gated by interval."""
        async def run():
            await self.scheduler.maybe_perceive()
            self.clock.advance(0.5)
            result = await self.scheduler.maybe_perceive()
            self.assertFalse(result)
        
        asyncio.run(run())
    
    def test_maybe_reflect_returns_true_when_called(self):
        """maybe_reflect should return True when actually called."""
        async def run():
            result = await self.scheduler.maybe_reflect()
            self.assertTrue(result)
        
        asyncio.run(run())
    
    def test_maybe_reflect_returns_false_when_gated(self):
        """maybe_reflect should return False when gated by in-flight task."""
        async def run():
            result = await self.scheduler.maybe_reflect()
            self.assertTrue(result)
            
            # Task is now in flight
            result = await self.scheduler.maybe_reflect()
            self.assertFalse(result)
        
        asyncio.run(run())


class ClockInjectionTests(unittest.TestCase):
    """Test clock injection for deterministic testing."""
    
    def test_clock_injection_works(self):
        """Injected clock should be used instead of real time."""
        clock = MockClock()
        scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=AsyncMock(),
            clock_fn=clock,
        )
        
        # Time should be controllable
        self.assertEqual(scheduler._now(), 0.0)
        clock.advance(5.5)
        self.assertEqual(scheduler._now(), 5.5)
    
    def test_clock_controls_interval_gates(self):
        """Clock injection should control interval gating behavior."""
        clock = MockClock()
        perception_calls = []
        
        async def perception_fn():
            perception_calls.append(clock.time)
        
        scheduler = ReflectionScheduler(
            perception_fn=perception_fn,
            reflection_fn=AsyncMock(),
            perception_interval_s=1.0,
            clock_fn=clock,
        )
        
        async def run():
            # First call at t=0
            await scheduler.maybe_perceive()
            self.assertEqual(len(perception_calls), 1)
            
            # At t=0.5, should be gated
            clock.advance(0.5)
            await scheduler.maybe_perceive()
            self.assertEqual(len(perception_calls), 1)
            
            # At t=1.0, should call
            clock.advance(0.5)
            await scheduler.maybe_perceive()
            self.assertEqual(len(perception_calls), 2)
        
        asyncio.run(run())


class CustomIntervalsTests(unittest.TestCase):
    """Test with custom interval values."""
    
    def test_custom_perception_interval(self):
        """Scheduler should respect custom perception interval."""
        clock = MockClock()
        perception_calls = []
        
        async def perception_fn():
            perception_calls.append(clock.time)
        
        scheduler = ReflectionScheduler(
            perception_fn=perception_fn,
            reflection_fn=AsyncMock(),
            perception_interval_s=0.5,  # Custom 500ms interval
            clock_fn=clock,
        )
        
        async def run():
            await scheduler.maybe_perceive()
            self.assertEqual(len(perception_calls), 1)
            
            clock.advance(0.3)
            await scheduler.maybe_perceive()
            self.assertEqual(len(perception_calls), 1)  # Still gated
            
            clock.advance(0.2)
            await scheduler.maybe_perceive()
            self.assertEqual(len(perception_calls), 2)  # Called at 0.5s
        
        asyncio.run(run())
    
    def test_custom_reflection_interval(self):
        """Scheduler should respect custom reflection interval."""
        clock = MockClock()
        
        scheduler = ReflectionScheduler(
            perception_fn=AsyncMock(),
            reflection_fn=AsyncMock(),
            reflection_interval_s=10.0,  # Custom 10s interval
            clock_fn=clock,
        )
        
        async def run():
            result = await scheduler.maybe_reflect()
            self.assertTrue(result)  # First call succeeds
            
            clock.advance(5.0)
            result = await scheduler.maybe_reflect()
            self.assertFalse(result)  # Gated at 5s
            
            clock.advance(5.0)
            # Wait for first task to complete
            await asyncio.sleep(0.01)
            result = await scheduler.maybe_reflect()
            self.assertTrue(result)  # Should be called now (10s elapsed)
        
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
