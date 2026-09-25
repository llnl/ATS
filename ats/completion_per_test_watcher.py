"""Per-test watcher completion detector for ATS machines."""

import threading

from ats.completion_waitpid_reaper import WaitpidReaperCompletionDetector


class PerTestWatcherCompletionDetector(WaitpidReaperCompletionDetector):
    """Use one ``Popen.wait`` watcher thread per launched test.

    Each watcher
    waits on the exact child process owned by its test, then enqueues that
    test for the shared fast-path drain.
    This detector is thread safe, but may not scale beyond a few nodes of
    concurrently running tests.
    """

    mode_name = "per_test_watcher"

    def owns_child_reaping(self):
        """Simple queue mode leaves child reaping to ``subprocess.Popen``."""
        return False

    def register_launched_test(self, test):
        """Start one watcher thread that waits for this child to exit."""
        child = getattr(test, "child", None)
        if child is None:
            return
        watcher = getattr(test, "_completionWatcher", None)
        if watcher is not None:
            self.machine._incrementCompletionStat("per_test_watcher_already_registered")
            return

        def watch_for_completion():
            """Wait for one child to exit and then enqueue its completion."""
            try:
                child.wait()
            except Exception:
                self.machine._incrementCompletionStat("per_test_watcher_wait_error")
                return
            self.machine._incrementCompletionStat("per_test_watcher_wait_completed")
            self.record_completion_signal(test)

        watcher = threading.Thread(
            target=watch_for_completion,
            name=f"ats-completion-{getattr(child, 'pid', 'unknown')}",
            daemon=True,
        )
        test._completionWatcher = watcher
        watcher.start()
        self.machine._incrementCompletionStat("per_test_watcher_registered")

    def unregister_finished_test(self, test):
        """Clear watcher bookkeeping for one finished test."""
        if hasattr(test, "_completionWatcher"):
            test._completionWatcher = None
            self.machine._incrementCompletionStat("per_test_watcher_cleared")
