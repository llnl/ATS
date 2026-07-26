"""Polling completion detector for ATS machines."""

import time

from ats.completion_detector import CompletionDetector
from ats.atsut import AtsError, PASSED


class PollingCompletionDetector(CompletionDetector):
    """Sleep-then-poll completion behavior."""

    mode_name = "poll"

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

    def poll_running_tests(
        self,
        allow_running_checks,
        completion_limit=None,
    ):
        """Poll running tests in scheduler order.

        Args:
            allow_running_checks (bool): When ``False``, skip timeout and
                runtime error checks for children that have not yet exited.
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

        ordered_count = 0
        completed = 0
        result_kind = "completed_none"
        try:
            ordered = list(machine.running)
            seen_ids = {id(test) for test in ordered}
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
                if completion_limit is not None and completed >= completion_limit:
                    remaining.extend(ordered[index + 1:])
                    self.preserve_new_running_tests(remaining, seen_ids)
                    machine.running = remaining
                    result_kind = "stopped_after_completion_limit"
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
                    "ordered_count": ordered_count,
                    "completion_limit": completion_limit,
                    "completed_count": completed,
                    "result": result_kind,
                },
            )


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

    def logCompletionWarnings(self, logger):
        """Polling mode has no detector-specific completion warnings."""
        return None
