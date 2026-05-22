from collections import deque
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from ats import configuration
from ats.atsut import AtsError, PASSED
from ats.completion_queue import CompletionQueueCompletionDetector
from ats.completion_detector import create_completion_detector
from ats.completion_legacy_poll import LegacyPollCompletionDetector
from ats.completion_queue_simple import CompletionQueueSimpleCompletionDetector
from ats.machines import Machine

if not hasattr(configuration, "options"):
    configuration.options = SimpleNamespace(
        oneFailure=False,
        verbose=False,
        skip=False,
        logUsage=False,
        removeStartNote=False,
        removeEndNote=False,
        debug=False,
    )


class _DetectorMachineStub:
    """Minimal machine stub for queue-detector focused unit tests."""

    def __init__(self, naptime=0.01):
        self.naptime = naptime
        self.running = []
        self.completion_detection_mode = "completion_queue"
        self.completion_fast_path_drain_limit = 128
        self._completionEvent = threading.Event()
        self._completionQueue = deque()
        self._completionQueueIds = set()
        self._completionQueueLock = threading.Lock()
        self.stats = {}
        self.get_status_calls = []
        self.health_scan_calls = 0

    def _incrementCompletionStat(self, name, amount=1):
        self.stats[name] = self.stats.get(name, 0) + amount

    def _recordCompletionInternalSpan(self, name, start_us, end_us, metadata=None):
        pass

    def _recordCompletionQueueSnapshot(self, depth, reason, timestamp_us=None, metadata=None):
        pass

    def getStatus(self, test, allow_running_checks=True):
        self.get_status_calls.append((test, allow_running_checks))
        if test.child.returncode is None:
            return False
        test.status = PASSED
        return True

    def scan_running_tests_for_health(self):
        self.health_scan_calls += 1
        return 0


class CompletionDetectorExamplesTest(unittest.TestCase):
    """Keep the scheduler-extension completion-detector examples executable."""

    def test_constructor_argument_selects_requested_completion_detector(self):
        """Constructor selection example should instantiate the requested detector."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="completion_queue",
        )

        self.assertEqual(machine.completion_detection_mode, "completion_queue")
        self.assertIsInstance(
            machine._completionDetector,
            CompletionQueueCompletionDetector,
        )

    def test_constructor_argument_selects_legacy_completion_detector(self):
        """Constructor selection should also support the legacy detector."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="legacy_poll",
        )

        self.assertEqual(machine.completion_detection_mode, "legacy_poll")
        self.assertIsInstance(
            machine._completionDetector,
            LegacyPollCompletionDetector,
        )

    def test_constructor_argument_selects_simple_queue_completion_detector(self):
        """Constructor selection should support the simple queue detector."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="completion_queue_simple",
        )

        self.assertEqual(machine.completion_detection_mode, "completion_queue_simple")
        self.assertIsInstance(
            machine._completionDetector,
            CompletionQueueSimpleCompletionDetector,
        )

    def test_completion_queue_is_the_default_when_no_mode_is_requested(self):
        """Default machine construction should preserve the queue detector."""
        machine = Machine("example", 1)

        self.assertEqual(machine.completion_detection_mode, "completion_queue")
        self.assertIsInstance(
            machine._completionDetector,
            CompletionQueueCompletionDetector,
        )

    def test_flux_direct_rejects_completion_queue_mode(self):
        """FluxDirect should reject the queued completion detector mode."""

        class FluxDirect:
            __module__ = "ats.atsMachines.FutureMachines.flux_direct"

        with self.assertRaisesRegex(AtsError, "unsupported for FluxDirect"):
            create_completion_detector(FluxDirect(), "completion_queue")

        with self.assertRaisesRegex(AtsError, "unsupported for FluxDirect"):
            create_completion_detector(FluxDirect(), "completion_queue_simple")

    def test_short_aliases_select_expected_detectors(self):
        """Short aliases should normalize to the expected detector types."""
        machine = Machine("example", 1, completion_detection_mode="poll")
        self.assertEqual(machine.completion_detection_mode, "legacy_poll")
        self.assertIsInstance(machine._completionDetector, LegacyPollCompletionDetector)

        machine = Machine("example", 1, completion_detection_mode="reap")
        self.assertEqual(machine.completion_detection_mode, "completion_queue")
        self.assertIsInstance(machine._completionDetector, CompletionQueueCompletionDetector)

        machine = Machine("example", 1, completion_detection_mode="queue")
        self.assertEqual(machine.completion_detection_mode, "completion_queue_simple")
        self.assertIsInstance(machine._completionDetector, CompletionQueueSimpleCompletionDetector)

    def test_queue_mode_does_not_call_child_poll(self):
        """Queue mode should trust reaper-populated return codes."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="completion_queue",
        )
        child = Mock()
        child.returncode = 17
        test = SimpleNamespace(child=child)

        self.assertEqual(machine._pollChild(test), 17)
        child.poll.assert_not_called()

    def test_legacy_mode_still_calls_child_poll(self):
        """Legacy polling mode should continue to use Popen.poll()."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="legacy_poll",
        )
        child = Mock()
        child.returncode = 0
        test = SimpleNamespace(child=child)

        self.assertEqual(machine._pollChild(test), 0)
        child.poll.assert_called_once_with()

    def test_simple_queue_mode_still_calls_child_poll(self):
        """Simple queue mode should still use Popen.poll() for completion checks."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="completion_queue_simple",
        )
        child = Mock()
        child.returncode = 0
        test = SimpleNamespace(child=child)

        self.assertEqual(machine._pollChild(test), 0)
        child.poll.assert_called_once_with()

    def test_completion_queue_reaper_sets_child_returncode(self):
        """Queue-mode reaper should publish subprocess-style return codes."""
        machine = _DetectorMachineStub()
        detector = CompletionQueueCompletionDetector(machine)
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(7)"],
        )
        test = SimpleNamespace(
            child=child,
            ats_completion_signal_us=None,
            status=PASSED,
        )

        detector.prepare_for_launch(test)
        self.assertTrue(machine._completionEvent.wait(5.0))

        deadline = time.time() + 5.0
        while child.returncode is None and time.time() < deadline:
            time.sleep(0.01)

        self.assertEqual(child.returncode, 7)
        self.assertEqual(detector.drain_completion_queue(), [test])

    def test_completion_queue_drain_avoids_fallback_completion_rescan(self):
        """Queue mode should only finalize queued completions and still scan health."""
        machine = _DetectorMachineStub()
        detector = CompletionQueueCompletionDetector(machine)
        queued_test = SimpleNamespace(
            child=SimpleNamespace(returncode=0),
            ats_completion_signal_us=None,
            status=PASSED,
        )
        still_running = SimpleNamespace(
            child=SimpleNamespace(returncode=None),
            ats_completion_signal_us=None,
            status=PASSED,
        )
        machine.running = [queued_test, still_running]

        detector.record_completion_signal(queued_test)
        detector.check_running()

        self.assertEqual(machine.get_status_calls, [(queued_test, False)])
        self.assertEqual(machine.health_scan_calls, 1)
        self.assertEqual(machine.running, [still_running])

    def test_completion_queue_records_unexpected_reaped_children(self):
        """Queue mode should record when waitpid reaps a non-test child."""
        machine = _DetectorMachineStub()
        detector = CompletionQueueCompletionDetector(machine)

        detector._handle_reaped_pid(4242, 0)

        self.assertEqual(machine.stats["completion_queue_reaper_unknown_pid"], 1)
        snapshot = detector._unexpectedReapsSnapshot()
        self.assertEqual(snapshot["count"], 1)
        self.assertEqual(snapshot["samples"][0]["pid"], 4242)
        self.assertEqual(snapshot["samples"][0]["outcome"], "exit 0")

    def test_completion_queue_logs_unexpected_completion_reap_warning(self):
        """Queue detector should summarize unexpected reaper events at end of run."""
        machine = _DetectorMachineStub()
        detector = CompletionQueueCompletionDetector(machine)
        messages = []

        def collect(message, **kwargs):
            del kwargs
            messages.append(message)

        detector._recordUnexpectedCompletionReap(111, 0)
        detector._recordUnexpectedCompletionReap(222, 9)
        detector.logCompletionWarnings(collect)

        self.assertEqual(len(messages), 3)
        self.assertIn("completion_queue reaped 2 child process(es)", messages[0])
        self.assertIn("pid=111", messages[1])
        self.assertIn("outcome=exit 0", messages[1])
        self.assertIn("pid=222", messages[2])
        self.assertIn("outcome=signal 9", messages[2])

    def test_legacy_detector_has_no_completion_warning_output(self):
        """Legacy detector should satisfy the warning interface with a no-op."""
        machine = Machine("example", 1, completion_detection_mode="legacy_poll")
        messages = []

        def collect(message, **kwargs):
            del kwargs
            messages.append(message)

        machine._completionDetector.logCompletionWarnings(collect)
        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
