import logging
import unittest

from pymumble_typed.callbacks import Callbacks, _BoundedPool


class _Recorder:
    """Minimal pool stand-in capturing what would be enqueued, without real threads."""

    def __init__(self):
        self.submitted = []

    def apply_async(self, run, args):
        # args is (callback, args); record the original callback for assertions.
        self.submitted.append(args[0])

    def close(self):
        pass

    def terminate(self):
        pass


class TestBoundedPoolShedding(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test")
        self.pool = _BoundedPool(1, 2, self.logger, "Test")
        self.recorder = _Recorder()
        # Replace the real ThreadPool so nothing actually runs; we only assert on what
        # gets enqueued vs. shed. _pending is never decremented (no _run executes), so the
        # bound is reached deterministically. Terminate the real pool first so it isn't
        # left orphaned to error out in its finalizer.
        self.pool._pool.terminate()
        self.pool._pool = self.recorder

    def test_sheddable_tasks_are_dropped_once_saturated(self):
        for _ in range(5):
            self.pool.submit(lambda: None, ())
        self.assertEqual(len(self.recorder.submitted), 2)  # limit reached, rest shed
        self.assertEqual(self.pool._shed, 3)

    def test_unsheddable_tasks_bypass_the_limit(self):
        for _ in range(5):
            self.pool.submit(lambda: None, (), sheddable=False)
        self.assertEqual(len(self.recorder.submitted), 5)
        self.assertEqual(self.pool._shed, 0)


class TestCallbacksOrderingGuarantees(unittest.TestCase):
    def test_control_pool_uses_a_single_worker(self):
        # Ordering of state callbacks depends on the control pool draining FIFO, which
        # only holds with exactly one worker.
        self.assertEqual(Callbacks.CONTROL_WORKERS, 1)

    def test_state_mutation_events_are_unsheddable(self):
        for name in (
            "on_user_created",
            "on_user_updated",
            "on_user_removed",
            "on_channel_created",
            "on_channel_updated",
            "on_channel_removed",
        ):
            self.assertIn(name, Callbacks._UNSHEDDABLE)


if __name__ == "__main__":
    unittest.main()
