"""Queued completion detector for ATS machines."""

import time

from ats.atsut import AtsError, PASSED
from ats.completion_legacy_poll import PollingCompletionDetector


class CompletionQueueCompletionDetector(PollingCompletionDetector):
    """Drain explicitly signaled completions from a machine-owned queue."""

    mode_name = "completion_queue"

    def wait_for_completion_signal(self):
        """Wait one polling interval for queued completion signals.

        Returns:
            list: Always returns an empty list because queue-mode wakeups only
            signal that queued completions may be available.
        """
        start_us = time.time_ns() // 1000
        machine = self.machine
        machine._incrementCompletionStat("_waitForCompletionSignal_called")
        result_kind = "queue_event_wait"
        try:
            machine._incrementCompletionStat("_waitForCompletionSignal_queue_event_wait")
            machine._completionEvent.wait(machine.naptime)
            return []
        finally:
            machine._recordCompletionInternalSpan(
                "_waitForCompletionSignal",
                start_us,
                time.time_ns() // 1000,
                metadata={
                    "mode": getattr(machine, "completion_detection_mode", ""),
                    "running_count": len(machine.running),
                    "registered": False,
                    "registered_count": 0,
                    "ready_count": 0,
                    "used_queue_event_wait": True,
                    "result": result_kind,
                },
            )

    def check_running(self):
        """Advance machine state by draining the queued completion set first.

        Returns:
            None: Completed tests may be finalized and removed from
            ``machine.running``.
        """
        machine = self.machine
        completion_limit = self.completion_drain_limit()
        machine._incrementCompletionStat("check_running_completion_queue_mode")
        if self.poll_queued_completion_tests(completion_limit=completion_limit):
            machine._incrementCompletionStat("check_running_queue_pre_drain_completed")
            return
        machine._incrementCompletionStat("check_running_queue_pre_drain_empty")
        machine._incrementCompletionStat("check_running_wait_for_completion_signal")
        self.wait_for_completion_signal()
        if self.poll_queued_completion_tests(completion_limit=completion_limit):
            machine._incrementCompletionStat("check_running_queue_post_wait_completed")
            return
        machine._incrementCompletionStat("check_running_queue_post_wait_empty")
        machine._incrementCompletionStat("check_running_queue_fallback_poll_running")
        self.poll_running_tests(
            allow_running_checks=True,
            completion_limit=completion_limit,
        )

    def record_completion_signal(self, test, observed_us=None):
        """Record a likely completion signal and enqueue it for later draining.

        Args:
            test: ATS test object associated with the completion signal.
            observed_us (int|None): Signal timestamp in microseconds. Uses the
                current time when omitted.

        Returns:
            None: Internal timestamps, queue state, and statistics are updated.
        """
        machine = self.machine
        super().record_completion_signal(test, observed_us=observed_us)
        if observed_us is None:
            observed_us = getattr(test, "ats_completion_signal_us", None)
        with machine._completionQueueLock:
            test_id = id(test)
            if test_id in machine._completionQueueIds:
                machine._incrementCompletionStat("completion_queue_duplicate_signal")
                return
            machine._completionQueue.append(test)
            machine._completionQueueIds.add(test_id)
            machine._completionEvent.set()
            machine._incrementCompletionStat("completion_queue_enqueued")
            depth = len(machine._completionQueue)
        machine._recordCompletionQueueSnapshot(
            depth,
            "completion_queue_enqueue",
            timestamp_us=observed_us,
        )

    def drain_completion_queue(self, completion_limit=None):
        """Remove queued completion candidates up to the configured limit.

        Args:
            completion_limit (int|None): Maximum number of queued tests to
                return. ``None`` drains the entire queue.

        Returns:
            list: Queued tests selected for completion re-checking.
        """
        machine = self.machine
        queued = []
        with machine._completionQueueLock:
            while machine._completionQueue:
                if completion_limit is not None and len(queued) >= completion_limit:
                    break
                test = machine._completionQueue.popleft()
                machine._completionQueueIds.discard(id(test))
                queued.append(test)
            remaining_depth = len(machine._completionQueue)
            if not machine._completionQueue:
                machine._completionEvent.clear()
        if queued:
            machine._recordCompletionQueueSnapshot(
                remaining_depth,
                "completion_queue_drain",
                metadata={
                    "drained_count": len(queued),
                    "completion_limit": completion_limit,
                },
            )
        return queued

    def poll_queued_completion_tests(self, completion_limit=None):
        """Handle completion candidates from the queued completion path.

        Args:
            completion_limit (int|None): Maximum number of queued candidates to
                process in this pass.

        Returns:
            int: Number of running tests confirmed completed in this pass.
        """
        from ats import configuration

        machine = self.machine
        start_us = time.time_ns() // 1000
        machine._incrementCompletionStat("_pollQueuedCompletionTests_called")
        queued_count = 0
        selected_count = 0
        stale_count = 0
        completed = 0
        result_kind = "empty"
        try:
            queued = self.drain_completion_queue(completion_limit=completion_limit)
            queued_count = len(queued)
            machine._incrementCompletionStat("_pollQueuedCompletionTests_total_queued", queued_count)
            if not queued:
                machine._incrementCompletionStat("_pollQueuedCompletionTests_empty")
                return 0

            selected = []
            selected_ids = set()
            running_ids = {id(test) for test in machine.running}
            for test in queued:
                test_id = id(test)
                if test_id in selected_ids:
                    continue
                if test_id not in running_ids:
                    stale_count += 1
                    continue
                selected.append(test)
                selected_ids.add(test_id)

            selected_count = len(selected)
            machine._incrementCompletionStat("_pollQueuedCompletionTests_total_selected", selected_count)
            machine._incrementCompletionStat("_pollQueuedCompletionTests_total_stale", stale_count)
            if stale_count:
                machine._incrementCompletionStat("_pollQueuedCompletionTests_saw_stale_entries")
            if not selected:
                result_kind = "stale_only"
                machine._incrementCompletionStat("_pollQueuedCompletionTests_selected_none")
                return 0

            completed_ids = set()
            for test in selected:
                done = machine.getStatus(test, allow_running_checks=False)
                if not done:
                    continue
                completed_ids.add(id(test))
                completed += 1
                if test.status is not PASSED and configuration.options.oneFailure:
                    raise AtsError("Test failed in oneFailure mode.")

            machine._incrementCompletionStat("_pollQueuedCompletionTests_total_completed", completed)
            if completed_ids:
                machine.running = [
                    test for test in machine.running if id(test) not in completed_ids
                ]
                result_kind = "completed"
                machine._incrementCompletionStat("_pollQueuedCompletionTests_completed")
            else:
                result_kind = "selected_none_completed"
                machine._incrementCompletionStat("_pollQueuedCompletionTests_selected_none_completed")
            return completed
        finally:
            machine._recordCompletionInternalSpan(
                "_pollQueuedCompletionTests",
                start_us,
                time.time_ns() // 1000,
                metadata={
                    "mode": getattr(machine, "completion_detection_mode", ""),
                    "completion_limit": completion_limit,
                    "queued_count": queued_count,
                    "selected_count": selected_count,
                    "stale_count": stale_count,
                    "completed_count": completed,
                    "result": result_kind,
                },
            )
