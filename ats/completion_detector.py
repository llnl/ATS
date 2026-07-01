"""Completion-detection strategy base class and factory helpers."""

from abc import ABC, abstractmethod

from ats.atsut import AtsError


def normalize_completion_detection_mode(mode):
    """Normalize a completion-detection mode string.

    Args:
        mode (str|None): Requested mode name.

    Returns:
        str: Normalized lowercase mode name, defaulting to
        ``"waitpid_reaper"``.
    """
    return str(mode or "waitpid_reaper").strip().lower() or "waitpid_reaper"


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
        normalized_mode in ("waitpid_reaper", "per_test_watcher")
        and machine_class == "FluxDirect"
        and machine_module.endswith("flux_direct")
    ):
        raise AtsError(
            "threaded completion detection is unsupported for FluxDirect. "
            "Use 'poll' for this experimental machine."
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

    def register_launched_test(self, test):
        """Prepare one launched test for detector-specific completion work.

        Args:
            test: ATS test object whose child process has just been launched.

        Returns:
            None: The default detector implementation needs no launch-time
            setup.
        """

    def unregister_finished_test(self, test):
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
    def logCompletionWarnings(self, logger):
        """Print any detector-specific end-of-run completion warnings.

        Args:
            logger (callable): Logging function compatible with ``ats.log.log``.

        Returns:
            None: Implementations may emit zero or more warnings.
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
    _validate_completion_detection_mode_for_machine(machine, normalized_mode)
    if normalized_mode == "waitpid_reaper":
        from ats.completion_waitpid_reaper import WaitpidReaperCompletionDetector

        return WaitpidReaperCompletionDetector(machine)
    if normalized_mode == "per_test_watcher":
        from ats.completion_per_test_watcher import PerTestWatcherCompletionDetector

        return PerTestWatcherCompletionDetector(machine)
    if normalized_mode == "poll":
        from ats.completion_poll import PollingCompletionDetector

        return PollingCompletionDetector(machine)
    raise AtsError(
        "Unknown completion detection mode %r. Expected one of: "
        "'waitpid_reaper', 'per_test_watcher', 'poll'." % mode
    )
