import unittest

from ats.atsut import AtsError
from ats.completion_queue import CompletionQueueCompletionDetector
from ats.completion_detector import create_completion_detector
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


if __name__ == "__main__":
    unittest.main()
