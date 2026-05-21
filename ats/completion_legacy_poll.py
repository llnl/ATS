"""Legacy polling completion detector for ATS machines."""

import time

from ats.completion_detector import CompletionDetector


class LegacyPollCompletionDetector(CompletionDetector):
    """Preserve the historical ATS double-poll-with-sleep behavior."""

    mode_name = "legacy_poll"

    @property
    def uses_signal_wait(self):
        """Return whether launch-time signal wait setup is needed.

        Returns:
            bool: Always ``False`` for the legacy polling detector.
        """
        return False

    def check_running(self):
        """Advance machine state using the historical polling behavior.

        Returns:
            None: Completed tests may be finalized and removed from
            ``machine.running``.
        """
        machine = self.machine
        completion_limit = self.completion_fast_path_drain_limit()
        if self.poll_running_tests(
            allow_running_checks=True,
            completion_limit=completion_limit,
        ):
            return
        time.sleep(machine.naptime)
        self.poll_running_tests(
            allow_running_checks=True,
            completion_limit=completion_limit,
        )
