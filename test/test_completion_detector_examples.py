import os
import unittest
from unittest import mock

from ats.completion_queue import CompletionQueueCompletionDetector
from ats.completion_fast_path import FastPathCompletionDetector
from ats.completion_legacy_poll import LegacyPollCompletionDetector
from ats.machines import Machine


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

    def test_environment_variable_selects_default_completion_detector(self):
        """Environment-selection example should influence default machine init."""
        with mock.patch.dict(
            os.environ,
            {"ATS_COMPLETION_DETECTION_MODE": "legacy_poll"},
            clear=False,
        ):
            machine = Machine("example", 1)

        self.assertEqual(machine.completion_detection_mode, "legacy_poll")
        self.assertIsInstance(
            machine._completionDetector,
            LegacyPollCompletionDetector,
        )

    def test_fast_path_is_the_default_when_no_mode_is_requested(self):
        """Default machine construction should preserve the fast-path detector."""
        with mock.patch.dict(os.environ, {}, clear=True):
            machine = Machine("example", 1)

        self.assertEqual(machine.completion_detection_mode, "fast_path")
        self.assertIsInstance(
            machine._completionDetector,
            FastPathCompletionDetector,
        )


if __name__ == "__main__":
    unittest.main()
