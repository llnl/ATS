"""Fast-path completion detector for ATS machines."""

from ats.completion_detector import CompletionDetector


class FastPathCompletionDetector(CompletionDetector):
    """Prefer signaled completions before slower running-state checks."""

    mode_name = "fast_path"

    def check_running(self):
        """Advance machine state using the fast completion-detection path.

        Returns:
            None: Completed tests may be finalized and removed from
            ``machine.running``.
        """
        completion_limit = self.completion_fast_path_drain_limit()
        if self.poll_running_tests(
            allow_running_checks=False,
            completion_limit=completion_limit,
        ):
            return
        completion_hints = self.wait_for_completion_signal()
        if completion_hints and self.poll_running_tests(
            allow_running_checks=False,
            prioritized=completion_hints,
            completion_limit=completion_limit,
        ):
            return
        self.poll_running_tests(allow_running_checks=True)
