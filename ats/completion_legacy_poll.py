"""Legacy polling detector and shared polling helpers for ATS machines."""

import time

from ats.atsut import AtsError, PASSED
from ats.completion_detector import CompletionDetector


class PollingCompletionDetector(CompletionDetector):
    """Shared polling helpers used by ATS completion detectors."""

    @property
    def uses_completion_queue(self):
        """Return whether completion signals should be queued.

        Returns:
            bool: ``True`` when signals should be enqueued for later draining.
        """
        return False

    def completion_drain_limit(self):
        """Return the configured maximum completions drained per wakeup.

        Returns:
            int: Positive completion drain limit.
        """
        limit = getattr(self.machine, "completion_fast_path_drain_limit", 128)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 128
        return max(1, limit)

    def prepare_for_launch(self, test):
        """Prepare one launched test for completion detection.

        Args:
            test: ATS test object whose child process has just been launched.

        Returns:
            None: Legacy polling does not need launch-time setup.
        """

    def close_for_test(self, test):
        """Release completion-detector resources associated with one test.

        Args:
            test: ATS test object that may own detector-specific wait state.

        Returns:
            None: Legacy polling does not need detector-specific cleanup.
        """

    def wait_for_completion_signal(self):
        """Wait for one scheduler polling interval.

        Returns:
            list: Always returns an empty list for polling-only waits.
        """
        start_us = time.time_ns() // 1000
        machine = self.machine
        machine._incrementCompletionStat("_waitForCompletionSignal_called")
        used_queue_event_wait = False
        result_kind = "sleep_fallback"
        try:
            if self.uses_completion_queue:
                used_queue_event_wait = True
                result_kind = "queue_event_wait"
                machine._incrementCompletionStat("_waitForCompletionSignal_queue_event_wait")
                machine._completionEvent.wait(machine.naptime)
                return []

            machine._incrementCompletionStat("_waitForCompletionSignal_sleep_fallback")
            time.sleep(machine.naptime)
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
                    "used_queue_event_wait": bool(used_queue_event_wait),
                    "result": result_kind,
                },
            )

    def poll_running_tests(
        self,
        allow_running_checks,
        prioritized=None,
        stop_after_completion=False,
        completion_limit=None,
    ):
        """Poll running tests, optionally prioritizing likely completions.

        Args:
            allow_running_checks (bool): When ``False``, skip timeout and
                runtime error checks for children that have not yet exited.
            prioritized (iterable|None): Optional running-test candidates to
                check before the rest of ``machine.running``.
            stop_after_completion (bool): If ``True``, stop after the first
                completed test is handled.
            completion_limit (int|None): Maximum number of completions to
                process before returning control to the scheduler.

        Returns:
            int: Number of completed tests processed in this polling pass.
        """
        from ats import configuration

        machine = self.machine
        start_us = time.time_ns() // 1000
        machine._incrementCompletionStat("_pollRunningTests_called")
        if allow_running_checks:
            machine._incrementCompletionStat("_pollRunningTests_allow_running_checks_true")
        else:
            machine._incrementCompletionStat("_pollRunningTests_allow_running_checks_false")

        prioritized = list(prioritized or [])
        prioritized_count = len(prioritized)
        ordered_count = 0
        completed = 0
        result_kind = "completed_none"
        try:
            ordered = []
            seen_ids = set()
            for test in prioritized:
                test_id = id(test)
                if test_id in seen_ids:
                    continue
                ordered.append(test)
                seen_ids.add(test_id)
            for test in machine.running:
                test_id = id(test)
                if test_id in seen_ids:
                    continue
                ordered.append(test)
                seen_ids.add(test_id)

            ordered_count = len(ordered)
            machine._incrementCompletionStat("_pollRunningTests_total_ordered", ordered_count)

            remaining = []
            for index, test in enumerate(ordered):
                done = machine.getStatus(test, allow_running_checks=allow_running_checks)
                if not done:
                    remaining.append(test)
                    continue
                completed += 1
                if test.status is not PASSED and configuration.options.oneFailure:
                    raise AtsError("Test failed in oneFailure mode.")
                if stop_after_completion or (
                    completion_limit is not None and completed >= completion_limit
                ):
                    remaining.extend(ordered[index + 1:])
                    self.preserve_new_running_tests(remaining, seen_ids)
                    machine.running = remaining
                    result_kind = "stopped_after_completion"
                    machine._incrementCompletionStat("_pollRunningTests_stopped_after_completion")
                    machine._incrementCompletionStat("_pollRunningTests_total_completed", completed)
                    return completed

            self.preserve_new_running_tests(remaining, seen_ids)
            machine.running = remaining
            machine._incrementCompletionStat("_pollRunningTests_total_completed", completed)
            if completed:
                result_kind = "completed"
                machine._incrementCompletionStat("_pollRunningTests_completed")
            else:
                machine._incrementCompletionStat("_pollRunningTests_completed_none")
            return completed
        finally:
            machine._recordCompletionInternalSpan(
                "_pollRunningTests",
                start_us,
                time.time_ns() // 1000,
                metadata={
                    "mode": getattr(machine, "completion_detection_mode", ""),
                    "allow_running_checks": bool(allow_running_checks),
                    "prioritized_count": prioritized_count,
                    "ordered_count": ordered_count,
                    "stop_after_completion": bool(stop_after_completion),
                    "completion_limit": completion_limit,
                    "completed_count": completed,
                    "result": result_kind,
                },
            )

    def preserve_new_running_tests(self, remaining, seen_ids):
        """Keep tests appended to ``machine.running`` during completion callbacks.

        Args:
            remaining (list): Running tests that should remain after the current
                polling pass.
            seen_ids (set): Object ids already considered in the polling pass.

        Returns:
            None: ``remaining`` is updated in place.
        """
        remaining_ids = {id(test) for test in remaining}
        for test in self.machine.running:
            test_id = id(test)
            if test_id in seen_ids or test_id in remaining_ids:
                continue
            remaining.append(test)
            remaining_ids.add(test_id)

    def record_completion_signal(self, test, observed_us=None):
        """Record a likely completion signal for one running test.

        Args:
            test: ATS test object associated with the completion signal.
            observed_us (int|None): Signal timestamp in microseconds. Uses the
                current time when omitted.

        Returns:
            None: Internal timestamps and statistics are updated.
        """
        machine = self.machine
        if observed_us is None:
            observed_us = time.time_ns() // 1000
        if getattr(test, "ats_completion_signal_us", None) is None:
            test.ats_completion_signal_us = observed_us
            machine._incrementCompletionStat("completion_signal_recorded")


class LegacyPollCompletionDetector(PollingCompletionDetector):
    """Preserve the plain ATS polling behavior from the ``ale3d`` branch."""

    mode_name = "legacy_poll"

    def check_running(self):
        """Advance machine state using plain sleep-then-poll behavior.

        Returns:
            None: Completed tests may be finalized and removed from
            ``machine.running``.
        """
        machine = self.machine
        time.sleep(machine.naptime)
        self.poll_running_tests(
            allow_running_checks=True,
        )
