"""Queued completion detector using one watcher thread per child."""

import threading

from ats.completion_queue import WaitpidReaperCompletionDetector


class PerTestWatcherCompletionDetector(WaitpidReaperCompletionDetector):
    """Preserve the original queued completion watcher-thread strategy."""

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
