"""Queued completion detector for ATS machines."""

import os
import threading
import time

from ats.atsut import AtsError, PASSED
from ats.completion_detector import CompletionDetector

# TODO: When we move to RHEL 5 or RHEL 6, migrate this to use pidfd instead of a reaper thread strategy.
class WaitpidReaperCompletionDetector(CompletionDetector):
    """Drain explicitly signaled completions from a machine-owned queue."""

    mode_name = "waitpid_reaper"

    def __init__(self, machine):
        """Initialize queue-mode reaper state for one ATS machine.

        Args:
            machine: Machine instance that owns queue-mode running tests.
        """
        super().__init__(machine)
        self._reaper_thread = None
        self._reaper_stop = False
        self._reaper_lock = threading.Lock()
        self._reaper_condition = threading.Condition(self._reaper_lock)
        self._registered_tests_by_pid = {}
        self._unexpected_reaps = []
        self._unexpected_reaps_count = 0
        self._unexpected_reaps_dropped = 0
        self._unexpected_reaps_lock = threading.Lock()

    def owns_child_reaping(self):
        """Queue mode owns child reaping through the detector reaper."""
        return True

    def _ensure_reaper_started(self):
        """Start the queue-mode reaper thread on first child registration."""
        if self._reaper_thread is not None:
            return
        self._reaper_thread = threading.Thread(
            target=self._reaper_loop,
            name="ats-completion-reaper",
            daemon=True,
        )
        self._reaper_thread.start()

    def _wait_status_to_returncode(self, wait_status):
        """Convert one raw wait status to subprocess-style return codes."""
        if os.WIFEXITED(wait_status):
            return os.WEXITSTATUS(wait_status)
        if os.WIFSIGNALED(wait_status):
            return -os.WTERMSIG(wait_status)
        return wait_status

    def _handle_reaped_pid(self, pid, wait_status):
        """Route one reaped child to the matching registered test if present."""
        machine = self.machine
        with self._reaper_condition:
            test = self._registered_tests_by_pid.pop(pid, None)

        if test is None:
            machine._incrementCompletionStat("completion_queue_reaper_unknown_pid")
            self._recordUnexpectedCompletionReap(pid, wait_status)
            return

        child = getattr(test, "child", None)
        if child is None:
            machine._incrementCompletionStat("completion_queue_reaper_missing_child")
            return

        child.returncode = self._wait_status_to_returncode(wait_status)
        machine._incrementCompletionStat("completion_queue_reaper_reaped")
        self.record_completion_signal(test)

    def _recordUnexpectedCompletionReap(self, pid, wait_status):
        """Remember one unexpectedly reaped child for end-of-run warnings."""
        observed_us = time.time_ns() // 1000
        if os.WIFEXITED(wait_status):
            outcome = "exit %d" % os.WEXITSTATUS(wait_status)
        elif os.WIFSIGNALED(wait_status):
            outcome = "signal %d" % os.WTERMSIG(wait_status)
        else:
            outcome = "wait_status %d" % wait_status
        sample = {
            "pid": pid,
            "wait_status": wait_status,
            "outcome": outcome,
            "observed_us": observed_us,
        }
        with self._unexpected_reaps_lock:
            self._unexpected_reaps_count += 1
            if len(self._unexpected_reaps) < 8:
                self._unexpected_reaps.append(sample)
            else:
                self._unexpected_reaps_dropped += 1

    def _unexpectedReapsSnapshot(self):
        """Return a snapshot of unexpected completion-reaper activity."""
        with self._unexpected_reaps_lock:
            return {
                "count": self._unexpected_reaps_count,
                "samples": list(self._unexpected_reaps),
                "dropped": self._unexpected_reaps_dropped,
            }

    def logCompletionWarnings(self, logger):
        """Print end-of-run warnings for suspicious queue-reaper events."""
        snapshot = self._unexpectedReapsSnapshot()
        if snapshot["count"] <= 0:
            logger(
                "WARNING: waitpid_reaper did not hit its known waitpid(-1) race in this run, "
                "but the risk remains. Use per_test_watcher if you need the safer path."
            )
            return
        logger(
            "WARNING: waitpid_reaper reaped %d child process(es) that were not "
            "registered ATS tests. This indicates the queue-mode reaper hit the "
            "known waitpid(-1) race and may have consumed another ATS subprocess "
            "exit status. This is especially an issue if wait_status!=0 for the pid." % snapshot["count"]
        )
        for sample in snapshot["samples"]:
            logger(
                "WARNING: unexpected reaped pid=%d outcome=%s wait_status=%d observed_us=%d"
                % (
                    sample["pid"],
                    sample["outcome"],
                    sample["wait_status"],
                    sample["observed_us"],
                )
            )
        if snapshot["dropped"]:
            logger(
                "WARNING: %d additional unexpected reaped child event(s) were not "
                "listed individually." % snapshot["dropped"]
            )

    def _reaper_loop(self):
        """Reap registered queue-mode children and enqueue their completions."""
        machine = self.machine
        while True:
            with self._reaper_condition:
                while not self._reaper_stop and not self._registered_tests_by_pid:
                    self._reaper_condition.wait()
                if self._reaper_stop and not self._registered_tests_by_pid:
                    return

            try:
                pid, wait_status = os.waitpid(-1, 0)
            except ChildProcessError:
                machine._incrementCompletionStat("completion_queue_reaper_child_process_error")
                with self._reaper_condition:
                    if not self._registered_tests_by_pid:
                        continue
                time.sleep(0.01)
                continue
            except OSError:
                machine._incrementCompletionStat("completion_queue_reaper_waitpid_error")
                time.sleep(0.01)
                continue

            self._handle_reaped_pid(pid, wait_status)

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

    def wait_for_completion_signal(self):
        """Wait one polling interval for queued completion signals.

        Returns:
            None: Will have waited for {machine.naptime} seconds, and updated appropriate
                  statistics and timing data.
        """
        start_us = time.time_ns() // 1000
        machine = self.machine
        machine._incrementCompletionStat("_waitForCompletionSignal_called")
        result_kind = "queue_event_wait"
        try:
            machine._incrementCompletionStat("_waitForCompletionSignal_queue_event_wait")
            machine._completionEvent.wait(machine.naptime)
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

    def register_launched_test(self, test):
        """Register one launched child with the queued completion reaper.

        Args:
            test: ATS test object whose child process has just been launched.

        Returns:
            None: The queue-mode reaper is started lazily and the child pid is
            registered for reaping.
        """
        child = getattr(test, "child", None)
        pid = getattr(child, "pid", None)
        if child is None or pid is None:
            return
        with self._reaper_condition:
            self._ensure_reaper_started()
            self._registered_tests_by_pid[pid] = test
            self._reaper_condition.notify()
        self.machine._incrementCompletionStat("completion_queue_reaper_registered")

    def unregister_finished_test(self, test):
        """Clear reaper bookkeeping for one finished test.

        Args:
            test: ATS test object that may still be registered with the queue
                reaper.

        Returns:
            None: Any stale pid registration is removed when present.
        """
        child = getattr(test, "child", None)
        pid = getattr(child, "pid", None)
        if pid is None:
            return
        with self._reaper_condition:
            registered = self._registered_tests_by_pid.get(pid)
            if registered is test:
                self._registered_tests_by_pid.pop(pid, None)

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
        else:
            machine._incrementCompletionStat("check_running_queue_pre_drain_empty")
            machine._incrementCompletionStat("check_running_wait_for_completion_signal")
            self.wait_for_completion_signal()
            if self.poll_queued_completion_tests(completion_limit=completion_limit):
                machine._incrementCompletionStat("check_running_queue_post_wait_completed")
            else:
                machine._incrementCompletionStat("check_running_queue_post_wait_empty")
        machine.scan_running_tests_for_health()

    def record_completion_signal(self, test):
        """Record a likely completion signal and enqueue it for later draining.

        Args:
            test: ATS test object associated with the completion signal.

        Returns:
            None: Internal timestamps, queue state, and statistics are updated.
        """
        machine = self.machine
        observed_us = time.time_ns() // 1000
        if getattr(test, "ats_completion_signal_us", None) is None:
            test.ats_completion_signal_us = observed_us
            machine._incrementCompletionStat("completion_signal_recorded")
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
