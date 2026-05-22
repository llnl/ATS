"""Completion-detection strategy base class and factory helpers."""

from abc import ABC, abstractmethod

from ats.atsut import AtsError


_COMPLETION_DETECTION_MODE_ALIASES = {
    "poll": "legacy_poll",
    "reap": "completion_queue",
    "queue": "completion_queue_simple",
}


def normalize_completion_detection_mode(mode):
    """Normalize a completion-detection mode string.

    Args:
        mode (str|None): Requested mode name.

    Returns:
        str: Normalized lowercase mode name, defaulting to
        ``"completion_queue"``.
    """
    normalized_mode = str(mode or "completion_queue").strip().lower() or "completion_queue"
    return _COMPLETION_DETECTION_MODE_ALIASES.get(normalized_mode, normalized_mode)


def _validate_completion_detection_mode_for_machine(machine, normalized_mode):
    """Reject detector modes unsupported by one machine implementation.

    Args:
        machine: Machine instance that would own the detector.
        normalized_mode (str): Normalized detector mode name.

    Returns:
        None: Validation succeeds without modifying ``machine``.

    Raises:
        AtsError: If ``normalized_mode`` is unsupported for ``machine``.
    """
    machine_class = machine.__class__.__name__
    machine_module = machine.__class__.__module__
    if (
        normalized_mode in ("completion_queue", "completion_queue_simple")
        and machine_class == "FluxDirect"
        and machine_module.endswith("flux_direct")
    ):
        raise AtsError(
            "queue-based completion detection is unsupported for FluxDirect. "
            "Use 'legacy_poll' or its alias 'poll' for this experimental machine."
        )


class CompletionDetector(ABC):
    """Abstract policy object with shared ATS completion-detection helpers."""

    mode_name = ""

    def __init__(self, machine):
        """Bind one completion detector to one ATS machine.

        Args:
            machine: Machine instance that owns completion helpers and running
                test state.

        Returns:
            None: The detector stores a reference to ``machine``.
        """
        self.machine = machine

    def prepare_for_launch(self, test):
        """Prepare one launched test for detector-specific completion work.

        Args:
            test: ATS test object whose child process has just been launched.

        Returns:
            None: The default detector implementation needs no launch-time
            setup.
        """

    def close_for_test(self, test):
        """Release detector-owned state associated with one finished test.

        Args:
            test: ATS test object that may own detector-specific wait state.

        Returns:
            None: The default detector implementation needs no cleanup.
        """

    def owns_child_reaping(self):
        """Return whether this detector is responsible for child reaping.

        Returns:
            bool: ``False`` for the default detector behavior.
        """
        return False

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
    _validate_completion_detection_mode_for_machine(machine, normalized_mode)
    if normalized_mode == "completion_queue":
        from ats.completion_queue import CompletionQueueCompletionDetector

        return CompletionQueueCompletionDetector(machine)
    if normalized_mode == "completion_queue_simple":
        from ats.completion_queue_simple import CompletionQueueSimpleCompletionDetector

        return CompletionQueueSimpleCompletionDetector(machine)
    if normalized_mode == "legacy_poll":
        from ats.completion_legacy_poll import LegacyPollCompletionDetector

        return LegacyPollCompletionDetector(machine)
    raise AtsError(
        "Unknown completion detection mode %r. Expected one of: "
        "'completion_queue', 'completion_queue_simple', 'legacy_poll' "
        "(aliases: 'reap', 'queue', 'poll')." % mode
    )
