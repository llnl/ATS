"""Queued completion detector for ATS machines."""

from ats.completion_detector import CompletionDetector


class CompletionQueueCompletionDetector(CompletionDetector):
    """Drain explicitly signaled completions from a machine-owned queue."""

    mode_name = "completion_queue"

    @property
    def uses_completion_queue(self):
        """Return whether completion signals should be queued.

        Returns:
            bool: Always ``True`` for the queued completion detector.
        """
        return True

    def check_running(self):
        """Advance machine state by draining the queued completion set first.

        Returns:
            None: Completed tests may be finalized and removed from
            ``machine.running``.
        """
        machine = self.machine
        completion_limit = machine._completionFastPathDrainLimit()
        machine._incrementCompletionStat("check_running_completion_queue_mode")
        if machine._pollQueuedCompletionTests(completion_limit=completion_limit):
            machine._incrementCompletionStat("check_running_queue_pre_drain_completed")
            return
        machine._incrementCompletionStat("check_running_queue_pre_drain_empty")
        machine._incrementCompletionStat("check_running_wait_for_completion_signal")
        self.wait_for_completion_signal()
        if machine._pollQueuedCompletionTests(completion_limit=completion_limit):
            machine._incrementCompletionStat("check_running_queue_post_wait_completed")
            return
        machine._incrementCompletionStat("check_running_queue_post_wait_empty")
        machine._incrementCompletionStat("check_running_queue_fallback_poll_running")
        machine._pollRunningTests(
            allow_running_checks=True,
            completion_limit=completion_limit,
        )
