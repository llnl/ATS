"""Completion-detection strategy interface and factory helpers."""

from abc import ABC, abstractmethod
import os

from ats.atsut import AtsError


def completion_detection_mode_from_env(default="fast_path"):
    """Return the configured completion-detection mode from the environment.

    Args:
        default (str): Mode used when the environment variable is unset.

    Returns:
        str: Requested completion-detection mode.
    """
    return os.environ.get("ATS_COMPLETION_DETECTION_MODE", default)


def normalize_completion_detection_mode(mode):
    """Normalize a completion-detection mode string.

    Args:
        mode (str|None): Requested mode name.

    Returns:
        str: Normalized lowercase mode name, defaulting to ``"fast_path"``.
    """
    return str(mode or "fast_path").strip().lower() or "fast_path"


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

    @property
    def uses_completion_queue(self):
        """Return whether completion signals should be queued.

        Returns:
            bool: ``True`` when signals should be enqueued for later draining.
        """
        return False

    @property
    def uses_signal_wait(self):
        """Return whether child-completion wait primitives should be prepared.

        Returns:
            bool: ``True`` when pidfds or watcher threads should be set up at
            launch time.
        """
        return True

    def prepare_for_launch(self, test):
        """Prepare one launched test for completion signaling.

        Args:
            test: ATS test object whose child process has just been launched.

        Returns:
            None: Completion wait primitives are installed when needed.
        """
        if self.uses_signal_wait:
            self.machine._ensurePidfd(test)

    def wait_for_completion_signal(self):
        """Wait for likely completions according to detector policy.

        Returns:
            list: Tests that were signaled as likely completed during the wait.
        """
        return self.machine._waitForCompletionSignal(
            use_queue_event_wait=self.uses_completion_queue,
        )

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
    if normalized_mode == "fast_path":
        from ats.completion_fast_path import FastPathCompletionDetector

        return FastPathCompletionDetector(machine)
    if normalized_mode == "completion_queue":
        from ats.completion_queue import CompletionQueueCompletionDetector

        return CompletionQueueCompletionDetector(machine)
    if normalized_mode == "legacy_poll":
        from ats.completion_legacy_poll import LegacyPollCompletionDetector

        return LegacyPollCompletionDetector(machine)
    raise AtsError(
        "Unknown completion detection mode %r. Expected one of: "
        "'fast_path', 'completion_queue', 'legacy_poll'." % mode
    )
