"""Completion-detection strategy interface and factory helpers."""

from abc import ABC, abstractmethod

from ats.atsut import AtsError


def normalize_completion_detection_mode(mode):
    """Normalize a completion-detection mode string.

    Args:
        mode (str|None): Requested mode name.

    Returns:
        str: Normalized lowercase mode name, defaulting to
        ``"completion_queue"``.
    """
    return str(mode or "completion_queue").strip().lower() or "completion_queue"


class CompletionDetector(ABC):
    """Abstract policy object for machine completion detection."""

    mode_name = ""

    def __init__(self, machine):
        """Bind one completion detector to one ATS machine.

        Args:
            machine: Machine instance that owns completion helpers and running
                test state.
        """
        self.machine = machine

    def prepare_for_launch(self, test):
        """Prepare one launched test for completion signaling.

        Args:
            test: ATS test object whose child process has just been launched.

        Returns:
            None: Default detector preparation is a no-op.
        """

    def close_for_test(self, test):
        """Release completion-detector resources associated with one test.

        Args:
            test: ATS test object that may own detector-specific wait state.

        Returns:
            None: Default detector cleanup is a no-op.
        """

    @abstractmethod
    def check_running(self):
        """Update machine running state according to one detector strategy.

        Returns:
            None: Implementations may finish tests and update ``machine.running``.
        """


def create_completion_detector(machine, mode):
    """Create one completion detector instance for the requested mode.

    Args:
        machine: Machine instance that will own the detector.
        mode (str|None): Requested detector mode.

    Returns:
        CompletionDetector: Strategy instance for the requested mode.

    Raises:
        AtsError: If ``mode`` is not one of the supported detector modes.
    """
    normalized_mode = normalize_completion_detection_mode(mode)
    if normalized_mode == "completion_queue":
        from ats.completion_queue import CompletionQueueCompletionDetector

        return CompletionQueueCompletionDetector(machine)
    if normalized_mode == "legacy_poll":
        from ats.completion_legacy_poll import LegacyPollCompletionDetector

        return LegacyPollCompletionDetector(machine)
    raise AtsError(
        "Unknown completion detection mode %r. Expected one of: "
        "'completion_queue', 'legacy_poll'." % mode
    )
