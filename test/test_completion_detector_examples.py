from collections import deque
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest

from ats import configuration
from ats.atsut import AtsError, PASSED
from ats.completion_waitpid_reaper import WaitpidReaperCompletionDetector
from ats.completion_detector import create_completion_detector
from ats.completion_per_test_watcher import PerTestWatcherCompletionDetector
from ats.completion_poll import PollingCompletionDetector
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
    """Minimal machine stub for completion-detector focused unit tests."""

    def __init__(self, naptime=0.01):
        self.naptime = naptime
        self.running = []
        self.completion_detection_mode = "waitpid_reaper"
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

    def test_constructor_argument_selects_waitpid_reaper_completion_detector_class(self):
        """Constructor selection should instantiate ``WaitpidReaperCompletionDetector``."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="waitpid_reaper",
        )

        self.assertEqual(machine.completion_detection_mode, "waitpid_reaper")
        self.assertIsInstance(
            machine._completionDetector,
            WaitpidReaperCompletionDetector,
        )

    def test_constructor_argument_selects_polling_completion_detector_class(self):
        """Constructor selection should instantiate ``PollingCompletionDetector``."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="poll",
        )

        self.assertEqual(machine.completion_detection_mode, "poll")
        self.assertIsInstance(
            machine._completionDetector,
            PollingCompletionDetector,
        )

    def test_constructor_argument_selects_per_test_watcher_completion_detector_class(self):
        """Constructor selection should instantiate ``PerTestWatcherCompletionDetector``."""
        machine = Machine(
            "example",
            1,
            completion_detection_mode="per_test_watcher",
        )

        self.assertEqual(machine.completion_detection_mode, "per_test_watcher")
        self.assertIsInstance(
            machine._completionDetector,
            PerTestWatcherCompletionDetector,
        )

    def test_waitpid_reaper_completion_detector_is_the_default_when_no_mode_is_requested(self):
        """Default machine construction should use ``WaitpidReaperCompletionDetector``."""
        machine = Machine("example", 1)

        self.assertEqual(machine.completion_detection_mode, "waitpid_reaper")
        self.assertIsInstance(
            machine._completionDetector,
            WaitpidReaperCompletionDetector,
        )

    def test_flux_direct_rejects_threaded_completion_modes(self):
        """FluxDirect should reject the threaded detector modes."""

        class FluxDirect:
            __module__ = "ats.atsMachines.FutureMachines.flux_direct"

        with self.assertRaisesRegex(AtsError, "unsupported for FluxDirect"):
            create_completion_detector(FluxDirect(), "waitpid_reaper")

        with self.assertRaisesRegex(AtsError, "unsupported for FluxDirect"):
            create_completion_detector(FluxDirect(), "per_test_watcher")

    def test_waitpid_reaper_sets_child_returncode(self):
        """``WaitpidReaperCompletionDetector`` should publish subprocess-style return codes."""
        machine = _DetectorMachineStub()
        detector = WaitpidReaperCompletionDetector(machine)
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(7)"],
        )
        test = SimpleNamespace(
            child=child,
            ats_completion_signal_us=None,
            status=PASSED,
        )

        detector.register_launched_test(test)
        self.assertTrue(machine._completionEvent.wait(5.0))

        deadline = time.time() + 5.0
        while child.returncode is None and time.time() < deadline:
            time.sleep(0.01)

        self.assertEqual(child.returncode, 7)
        self.assertEqual(detector.drain_completion_queue(), [test])

    def test_waitpid_reaper_drain_avoids_fallback_completion_rescan(self):
        """``WaitpidReaperCompletionDetector`` should only finalize queued completions and scan health."""
        machine = _DetectorMachineStub()
        detector = WaitpidReaperCompletionDetector(machine)
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

    def test_waitpid_reaper_records_unexpected_reaped_children(self):
        """``WaitpidReaperCompletionDetector`` should record when waitpid reaps a non-test child."""
        machine = _DetectorMachineStub()
        detector = WaitpidReaperCompletionDetector(machine)

        detector._handle_reaped_pid(4242, 0)

        self.assertEqual(machine.stats["completion_queue_reaper_unknown_pid"], 1)
        snapshot = detector._unexpectedReapsSnapshot()
        self.assertEqual(snapshot["count"], 1)
        self.assertEqual(snapshot["samples"][0]["pid"], 4242)
        self.assertEqual(snapshot["samples"][0]["outcome"], "exit 0")

    def test_waitpid_reaper_logs_unexpected_completion_reap_warning(self):
        """``WaitpidReaperCompletionDetector`` should summarize unexpected reaper events at end of run."""
        machine = _DetectorMachineStub()
        detector = WaitpidReaperCompletionDetector(machine)
        messages = []

        def collect(message, **_kwargs):
            messages.append(message)

        detector._recordUnexpectedCompletionReap(111, 0)
        detector._recordUnexpectedCompletionReap(222, 9)
        detector.logCompletionWarnings(collect)

        self.assertEqual(len(messages), 3)
        self.assertIn("waitpid_reaper reaped 2 child process(es)", messages[0])
        self.assertIn("pid=111", messages[1])
        self.assertIn("outcome=exit 0", messages[1])
        self.assertIn("pid=222", messages[2])
        self.assertIn("outcome=signal 9", messages[2])

if __name__ == "__main__":
    unittest.main()
