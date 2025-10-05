
# tests/performance.py
"""
Performance testing utilities and benchmarks.
"""
import time
from django.test import TestCase


class PerformanceTestCase(TestCase):
    """Base class for performance tests."""
    
    def setUp(self):
        self.start_time = None
        self.end_time = None
    
    def start_timer(self):
        """Start performance timer."""
        self.start_time = time.time()
    
    def end_timer(self):
        """End performance timer."""
        self.end_time = time.time()
        return self.end_time - self.start_time if self.start_time else None
    
    def assertTimeUnder(self, max_time, msg=None):
        """Assert that elapsed time is under max_time seconds."""
        elapsed = self.end_timer()
        if elapsed is None:
            self.fail("Timer not started")
        
        if msg is None:
            msg = f"Operation took {elapsed:.3f}s, expected under {max_time}s"
        
        self.assertLessEqual(elapsed, max_time, msg)

