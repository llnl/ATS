"""Definition of class Machine for overriding.
"""
from collections import deque
import selectors, subprocess, sys, os, threading, time, shlex
from ats.atsut import RUNNING, TIMEDOUT, PASSED, FAILED, LSFERROR, \
     SKIPPED, HALTED, AtsError
from ats.log import log, terminal
from shutil import copytree, ignore_patterns

def comparePriorities(t1, t2):
    "Input is two tests; return comparison based on totalPriority."
    return t2.totalPriority - t1.totalPriority

#-----------------------------------------------------------
# class MachineCore
#-----------------------------------------------------------
class MachineCore(object):
    """Invariable parts of a machine. Not capable of being instantiated"""

    debugClass = False
    canRunNow_debugClass = False
    printExperimentalNotice = False
    printSleepBeforeSrunNotice = True

    # self.numberTestsRunningMax is not really the max number of tests running
    # but is rather the max number of processors which can run tests.
    def label(self):
        return '%s(%d)' % (self.name, self.numberTestsRunningMax)

    def split(self, astring):
        "Correctly split a clas string into a list of arguments for this machine."
        return shlex.split(astring)

    def calculateBasicCommandList(self, test):
        """Prepare for run of executable using a suitable command.
           Returns the plain command line that would be executed on a vanilla
           machine.
        """
        return test.executable.commandList + test.clas

    def examineBasicOptions(self, options):
        "Examine options from command line, possibly override command line choices."
        from ats import configuration
        if configuration.options.sequential:
            self.numberTestsRunningMax = 1
        elif self.hardLimit:
            if options.npMax > 0:
                self.numberTestsRunningMax = options.npMax
        else:
            if options.npMax > 0:
                self.numberTestsRunningMax = options.npMax

    def checkForTimeOut(self, test):
        """ Check the time elapsed since test's start time.  If greater
        then the timelimit, return true, else return false.  test's
        end time is set if time elapsed exceeds time limit """
        from ats import configuration

        timeNow = time.time()
        # Add small increment to flags jobs that 
        # are close to timing out as timing out. Without this
        # they were occasionally mis categorized as FAILED in
        # later processing.
        timePassed = (timeNow - test.startTime) + 0.2
        #cut = configuration.cuttime
        fraction = timePassed / test.timelimit.value

        # ATS will defer timeouts to the flux scheduler and will
        #     not implement timeouts within the ATS code.
        #     This is because the time a job is submitted to flux 
        #     and the time it actually starts are not equivalent
        #     So the timelimits or cutoffs will be passed to flux 
        #     for processing.
        if "flux" in configuration.MACHINE_TYPE:
            return 0, 0
            # print("SAD DEBUG checkForTimeOut always returns 0 under flux\n")

        if (timePassed < 0):         # system clock change, reset start time
            test.setStartTimeDate()
        elif (timePassed >= test.timelimit.value):   # process timed out
            return 1, fraction
        # elif cut is not None and timePassed >= cut.value:
        #     return -1, fraction
        return 0, fraction

    def checkRunning(self):
        """Find those tests still running. getStatus checks for timeout.
        """
        completion_limit = self._completionFastPathDrainLimit()
        if self._useLegacyCompletionPolling():
            if self._pollRunningTests(
                allow_running_checks=True,
                completion_limit=completion_limit,
            ):
                return
            time.sleep(self.naptime)
            self._pollRunningTests(
                allow_running_checks=True,
                completion_limit=completion_limit,
            )
            return
        if self._useQueuedCompletionDetection():
            self._incrementCompletionStat("check_running_completion_queue_mode")
            if self._pollQueuedCompletionTests(completion_limit=completion_limit):
                self._incrementCompletionStat("check_running_queue_pre_drain_completed")
                return
            self._incrementCompletionStat("check_running_queue_pre_drain_empty")
            self._incrementCompletionStat("check_running_wait_for_completion_signal")
            self._waitForCompletionSignal()
            if self._pollQueuedCompletionTests(completion_limit=completion_limit):
                self._incrementCompletionStat("check_running_queue_post_wait_completed")
                return
            self._incrementCompletionStat("check_running_queue_post_wait_empty")
            self._incrementCompletionStat("check_running_queue_fallback_poll_running")
            self._pollRunningTests(
                allow_running_checks=True,
                completion_limit=completion_limit,
            )
            return
        if self._pollRunningTests(
            allow_running_checks=False,
            completion_limit=completion_limit,
        ):
            return
        completion_hints = self._waitForCompletionSignal()
        if completion_hints and self._pollRunningTests(
            allow_running_checks=False,
            prioritized=completion_hints,
            completion_limit=completion_limit,
        ):
            return
        self._pollRunningTests(allow_running_checks=True)

    def remainingCapacity(self):
        """How many processors are free? Could be overriden to answer the real question,
           what is the largest job you could start at this time?"""
        return self.numberTestsRunningMax - self.numberTestsRunning

    def getStatus(self, test, allow_running_checks=True):
        """
        Override this only if not using subprocess (unusual).
        Obtains the exit code of the test object process and then sets
        the status of the test object accordingly. Returns True if test done.

        When a test has completed you must set test.statusCode and
        call self.testEnded(test, status). You may add a message as a third arg,
        which will be shown in the test's final report.
        testEnded will call your bookkeeping method noteEnd.
        """
        from ats import configuration
        self._pollChild(test)
        if test.child.returncode is not None:
            return self._finishCompletedTest(test)

        if not allow_running_checks:
            return False

        overtime, fraction = self.checkForTimeOut(test)
        if fraction > .9 or overtime != 0:
            if configuration.SYS_TYPE.startswith('somesystemxxx'):
                stdoutdata, stderrdata = test.child.communicate()

            self._pollChild(test)
            if test.child.returncode is not None:
                return self._finishCompletedTest(test)

        overtime, fraction = self.checkForTimeOut(test)
        if overtime != 0:
            self.kill(test)
            test.statusCode = 2
            test.setEndDateTime()
            if overtime > 0:
                status = TIMEDOUT
            else:
                status = HALTED
            return self._completeTest(test, status)

        if self._detectRunningSlurmError(test):
            self.kill(test)
            test.statusCode = 2
            test.setEndDateTime()
            return self._completeTest(test, HALTED)

        return False

    def _pollRunningTests(
        self,
        allow_running_checks,
        prioritized=None,
        stop_after_completion=False,
        completion_limit=None,
    ):
        """Poll running tests, optionally prioritizing likely completions."""
        from ats import configuration

        start_us = time.time_ns() // 1000
        self._incrementCompletionStat("_pollRunningTests_called")
        if allow_running_checks:
            self._incrementCompletionStat("_pollRunningTests_allow_running_checks_true")
        else:
            self._incrementCompletionStat("_pollRunningTests_allow_running_checks_false")

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
            for test in self.running:
                test_id = id(test)
                if test_id in seen_ids:
                    continue
                ordered.append(test)
                seen_ids.add(test_id)

            ordered_count = len(ordered)
            self._incrementCompletionStat("_pollRunningTests_total_ordered", ordered_count)

            remaining = []
            for index, test in enumerate(ordered):
                done = self.getStatus(test, allow_running_checks=allow_running_checks)
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
                    self._preserve_new_running_tests(remaining, seen_ids)
                    self.running = remaining
                    result_kind = "stopped_after_completion"
                    self._incrementCompletionStat("_pollRunningTests_stopped_after_completion")
                    self._incrementCompletionStat("_pollRunningTests_total_completed", completed)
                    return completed

            self._preserve_new_running_tests(remaining, seen_ids)
            self.running = remaining
            self._incrementCompletionStat("_pollRunningTests_total_completed", completed)
            if completed:
                result_kind = "completed"
                self._incrementCompletionStat("_pollRunningTests_completed")
            else:
                self._incrementCompletionStat("_pollRunningTests_completed_none")
            return completed
        finally:
            self._recordCompletionInternalSpan(
                "_pollRunningTests",
                start_us,
                time.time_ns() // 1000,
                metadata={
                    "mode": getattr(self, "completion_detection_mode", ""),
                    "allow_running_checks": bool(allow_running_checks),
                    "prioritized_count": prioritized_count,
                    "ordered_count": ordered_count,
                    "stop_after_completion": bool(stop_after_completion),
                    "completion_limit": completion_limit,
                    "completed_count": completed,
                    "result": result_kind,
                },
            )

    def _preserve_new_running_tests(self, remaining, seen_ids):
        """Keep tests appended to ``self.running`` during completion callbacks."""
        remaining_ids = {id(test) for test in remaining}
        for test in self.running:
            test_id = id(test)
            if test_id in seen_ids or test_id in remaining_ids:
                continue
            remaining.append(test)
            remaining_ids.add(test_id)

    def _waitForCompletionSignal(self):
        """Wait for a local child exit, using pidfds when available."""
        start_us = time.time_ns() // 1000
        self._incrementCompletionStat("_waitForCompletionSignal_called")
        registered = False
        registered_count = 0
        ready = []
        selector = None
        used_queue_event_wait = False
        result_kind = "sleep_fallback"
        try:
            selector = selectors.DefaultSelector()
        except Exception:
            selector = None

        try:
            if selector is not None:
                try:
                    for test in self.running:
                        pidfd = self._ensurePidfd(test)
                        if pidfd is None:
                            continue
                        try:
                            selector.register(pidfd, selectors.EVENT_READ, test)
                            registered = True
                            registered_count += 1
                        except Exception:
                            self._closePidfd(test)
                    if registered:
                        self._incrementCompletionStat("_waitForCompletionSignal_pidfd_registered")
                        ready = [key.data for key, _mask in selector.select(self.naptime)]
                        if ready:
                            result_kind = "pidfd_ready"
                            self._incrementCompletionStat("_waitForCompletionSignal_pidfd_ready")
                            self._incrementCompletionStat("_waitForCompletionSignal_total_ready", len(ready))
                            for test in ready:
                                self._recordCompletionSignal(test)
                        else:
                            result_kind = "pidfd_timeout"
                            self._incrementCompletionStat("_waitForCompletionSignal_pidfd_timeout")
                finally:
                    selector.close()

            if registered:
                return ready

            if self._useQueuedCompletionDetection():
                used_queue_event_wait = True
                result_kind = "queue_event_wait"
                self._incrementCompletionStat("_waitForCompletionSignal_queue_event_wait")
                self._completionEvent.wait(self.naptime)
                return []

            self._incrementCompletionStat("_waitForCompletionSignal_sleep_fallback")
            time.sleep(self.naptime)
            return []
        finally:
            self._recordCompletionInternalSpan(
                "_waitForCompletionSignal",
                start_us,
                time.time_ns() // 1000,
                metadata={
                    "mode": getattr(self, "completion_detection_mode", ""),
                    "running_count": len(self.running),
                    "registered": bool(registered),
                    "registered_count": registered_count,
                    "ready_count": len(ready),
                    "used_queue_event_wait": bool(used_queue_event_wait),
                    "result": result_kind,
                },
            )

    def _useLegacyCompletionPolling(self):
        mode = str(getattr(self, "completion_detection_mode", "") or "").strip().lower()
        return mode == "legacy_poll"

    def _useQueuedCompletionDetection(self):
        mode = str(getattr(self, "completion_detection_mode", "") or "").strip().lower()
        return mode == "completion_queue"

    def _completionStatsEnabled(self):
        return bool(getattr(self, "completion_detection_stats", False))

    def _completionSpansEnabled(self):
        return bool(getattr(self, "completion_detection_spans", False))

    def _incrementCompletionStat(self, name, amount=1):
        if not self._completionStatsEnabled():
            return
        with self._completionStatsLock:
            self._completionStats[name] = self._completionStats.get(name, 0) + amount

    def _completionStatsSnapshot(self):
        with self._completionStatsLock:
            return dict(self._completionStats)

    def _addMachineHook(self, hook_attr, callback, description):
        if not callable(callback):
            raise AtsError("%s hook must be callable" % description)
        hooks = getattr(self, hook_attr, None)
        if hooks is None:
            hooks = []
            setattr(self, hook_attr, hooks)
        hooks.append(callback)
        return callback

    def _removeMachineHook(self, hook_attr, callback):
        hooks = getattr(self, hook_attr, None)
        if hooks is None:
            return
        try:
            hooks.remove(callback)
        except ValueError:
            pass

    def add_completion_span_hook(self, callback):
        """Register a callback for internal completion-detection timing spans."""
        return self._addMachineHook(
            "_completion_span_hooks",
            callback,
            "completion span",
        )

    def remove_completion_span_hook(self, callback):
        """Unregister a completion span callback."""
        self._removeMachineHook("_completion_span_hooks", callback)

    def add_completion_queue_snapshot_hook(self, callback):
        """Register a callback for completion queue depth snapshots."""
        return self._addMachineHook(
            "_completion_queue_snapshot_hooks",
            callback,
            "completion queue snapshot",
        )

    def remove_completion_queue_snapshot_hook(self, callback):
        """Unregister a completion queue snapshot callback."""
        self._removeMachineHook("_completion_queue_snapshot_hooks", callback)

    def _recordCompletionInternalSpan(self, name, start_us, end_us, metadata=None):
        if not self._completionSpansEnabled():
            return
        for callback in list(getattr(self, "_completion_span_hooks", [])):
            callback(name, start_us, end_us, metadata or {})

    def _recordCompletionQueueSnapshot(self, depth, reason, timestamp_us=None, metadata=None):
        if timestamp_us is None:
            timestamp_us = time.time_ns() // 1000
        depth = max(0, int(depth))
        if self._completionStatsEnabled():
            with self._completionStatsLock:
                self._completionStats["completion_queue_depth_latest"] = depth
                peak = int(self._completionStats.get("completion_queue_depth_peak", 0))
                if depth > peak:
                    self._completionStats["completion_queue_depth_peak"] = depth
        payload = {
            "completion_queue_depth": depth,
            "reason": reason,
        }
        if metadata:
            payload.update(metadata)
        for callback in list(getattr(self, "_completion_queue_snapshot_hooks", [])):
            callback(timestamp_us, payload)

    def _completionFastPathDrainLimit(self):
        limit = getattr(self, "completion_fast_path_drain_limit", 128)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 128
        return max(1, limit)

    def _pollChild(self, test):
        test.child.poll()
        return test.child.returncode

    def _recordCompletionSignal(self, test, observed_us=None):
        if observed_us is None:
            observed_us = time.time_ns() // 1000
        if getattr(test, "ats_completion_signal_us", None) is None:
            test.ats_completion_signal_us = observed_us
            self._incrementCompletionStat("completion_signal_recorded")
        if not self._useQueuedCompletionDetection():
            return
        with self._completionQueueLock:
            test_id = id(test)
            if test_id in self._completionQueueIds:
                self._incrementCompletionStat("completion_queue_duplicate_signal")
                return
            self._completionQueue.append(test)
            self._completionQueueIds.add(test_id)
            self._completionEvent.set()
            self._incrementCompletionStat("completion_queue_enqueued")
            depth = len(self._completionQueue)
        self._recordCompletionQueueSnapshot(
            depth,
            "completion_queue_enqueue",
            timestamp_us=observed_us,
        )

    def _drainCompletionQueue(self, completion_limit=None):
        queued = []
        with self._completionQueueLock:
            while self._completionQueue:
                if completion_limit is not None and len(queued) >= completion_limit:
                    break
                test = self._completionQueue.popleft()
                self._completionQueueIds.discard(id(test))
                queued.append(test)
            remaining_depth = len(self._completionQueue)
            if not self._completionQueue:
                self._completionEvent.clear()
        if queued:
            self._recordCompletionQueueSnapshot(
                remaining_depth,
                "completion_queue_drain",
                metadata={
                    "drained_count": len(queued),
                    "completion_limit": completion_limit,
                },
            )
        return queued

    def _pollQueuedCompletionTests(self, completion_limit=None):
        from ats import configuration

        start_us = time.time_ns() // 1000
        self._incrementCompletionStat("_pollQueuedCompletionTests_called")
        queued_count = 0
        selected_count = 0
        stale_count = 0
        completed = 0
        result_kind = "empty"
        try:
            queued = self._drainCompletionQueue(completion_limit=completion_limit)
            queued_count = len(queued)
            self._incrementCompletionStat("_pollQueuedCompletionTests_total_queued", queued_count)
            if not queued:
                self._incrementCompletionStat("_pollQueuedCompletionTests_empty")
                return 0

            selected = []
            selected_ids = set()
            running_ids = {id(test) for test in self.running}
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
            self._incrementCompletionStat("_pollQueuedCompletionTests_total_selected", selected_count)
            self._incrementCompletionStat("_pollQueuedCompletionTests_total_stale", stale_count)
            if stale_count:
                self._incrementCompletionStat("_pollQueuedCompletionTests_saw_stale_entries")
            if not selected:
                result_kind = "stale_only"
                self._incrementCompletionStat("_pollQueuedCompletionTests_selected_none")
                return 0

            completed_ids = set()
            for test in selected:
                done = self.getStatus(test, allow_running_checks=False)
                if not done:
                    continue
                completed_ids.add(id(test))
                completed += 1
                if test.status is not PASSED and configuration.options.oneFailure:
                    raise AtsError("Test failed in oneFailure mode.")

            self._incrementCompletionStat("_pollQueuedCompletionTests_total_completed", completed)
            if completed_ids:
                self.running = [
                    test for test in self.running if id(test) not in completed_ids
                ]
                result_kind = "completed"
                self._incrementCompletionStat("_pollQueuedCompletionTests_completed")
            else:
                result_kind = "selected_none_completed"
                self._incrementCompletionStat("_pollQueuedCompletionTests_selected_none_completed")
            return completed
        finally:
            self._recordCompletionInternalSpan(
                "_pollQueuedCompletionTests",
                start_us,
                time.time_ns() // 1000,
                metadata={
                    "mode": getattr(self, "completion_detection_mode", ""),
                    "completion_limit": completion_limit,
                    "queued_count": queued_count,
                    "selected_count": selected_count,
                    "stale_count": stale_count,
                    "completed_count": completed,
                    "result": result_kind,
                },
            )

    def _finishCompletedTest(self, test):
        from ats import configuration

        if getattr(test, "ats_returncode_observed_us", None) is None:
            test.ats_returncode_observed_us = time.time_ns() // 1000
        test.setEndDateTime()
        test.statusCode = test.child.returncode
        ignoreReturnCode  = test.options.get('ignoreReturnCode', False)
        if ignoreReturnCode:
            test.statusCode = 0
        if test.statusCode == 0:
            status = PASSED
        elif "flux" in configuration.MACHINE_TYPE and test.statusCode == 142:
            status = TIMEDOUT
        else:
            lsf_error = False
            with open(test.errname, 'r', errors='replace') as f:
                lines = f.readlines()
            for line in lines:
                if lsf_error == False:
                    if "Terminated while pending" in line:
                        print("ATS ERROR: Detected LSF Job Start Error %s.  Detected LSF launch failure : %s " % (test.name, line))
                        lsf_error = True
                    elif "JSM daemon timed" in line:
                        print("ATS ERROR: Detected LSF Job Start Error %s.  Detected LSF launch failure : %s " % (test.name, line))
                        lsf_error = True
                    elif "Error initializing RM" in line:
                        print("ATS ERROR: Detected LSF Job Start Error %s.  Detected LSF launch failure : %s " % (test.name, line))
                        lsf_error = True
                    elif "Bus error)" in line:
                        print("ATS ERROR: Halting test %s. Detected Bus Error (perhaps MPI related) : %s " % (test.name, line))
                        lsf_error = True

            if not lsf_error:
                with open(test.outname, 'r', errors='replace') as f:
                    lines = f.readlines()
                for line in lines:
                    if lsf_error == False:
                        if "ATS Error: Locate pipe file" in line:
                            print("ATS ERROR: Detected LSF Job Start Error %s.  Detected LSF launch failure : %s " % (test.name, line))
                            lsf_error = True
                        elif "Could not read jskill" in line:
                            print("ATS ERROR: Detected LSF Job Scheduler Error %s.  : %s " % (test.name, line))
                            lsf_error = True
                        elif "AST Error: initializing RM" in line:
                            print("ATS ERROR: Detected LSF Job Start Error %s.  Detected LSF launch failure : %s " % (test.name, line))
                            lsf_error = True

            if lsf_error:
                print("ATS LSF Development: LSFE Detected statusCode is %d " % test.statusCode)
                test.statusCode = 2
                test.setEndDateTime()
                status = LSFERROR
            else:
                status = FAILED

        return self._completeTest(test, status)

    def _completeTest(self, test, status):
        if test.stdOutLocGet() == 'both':
            outhandle, errhandle = test.fileHandleGet()
            for line in test.child.stdout:
                print(line)
                print(line, file=outhandle)

        self._closePidfd(test)
        self.testEnded(test, status)
        return True

    def _detectRunningSlurmError(self, test):
        with open(test.errname, 'r', errors='replace') as f:
            lines = f.readlines()
        for line in lines:
            if "Slurmd could not set up environment for batch job" in line:
                print("ATS Halting test %s. Detected slurm launch failure : %s " % (test.name, line))
                return True
            elif "srun: error: Unable to create job step" in line:
                print("ATS Halting test %s. Detected slurm error : %s " % (test.name, line))
                return True
            elif "Error opening remote shared memory object in shm_open" in line:
                print("ATS Halting test %s. Detected MPI shared memory failure : %s " % (test.name, line))
                return True
            elif "PSM could not set up shared memory segment" in line:
                print("ATS Halting test %s. Detected MPI shared memory failure : %s " % (test.name, line))
                return True
            elif "Attempting to use an MPI routine before initializing MPICH" in line:
                print("ATS Halting test %s. Detected MPI Error : %s " % (test.name, line))
                return True
            elif "Bus error)" in line:
                print("ATS Halting test %s. Detected Bus Error (perhaps MPI related) : %s " % (test.name, line))
                return True
        return False

    def _ensurePidfd(self, test):
        if getattr(self, "_pidfdUnavailable", False):
            self._ensureCompletionWatcher(test)
            return None
        pidfd = getattr(test, "_pidfd", None)
        if pidfd is not None:
            return pidfd
        if not hasattr(os, "pidfd_open"):
            self._pidfdUnavailable = True
            self._ensureCompletionWatcher(test)
            return None
        child = getattr(test, "child", None)
        if child is None or getattr(child, "pid", None) is None:
            return None
        try:
            pidfd = os.pidfd_open(child.pid)
        except OSError:
            self._ensureCompletionWatcher(test)
            return None
        except AttributeError:
            self._pidfdUnavailable = True
            self._ensureCompletionWatcher(test)
            return None
        test._pidfd = pidfd
        return pidfd

    def _ensureCompletionWatcher(self, test):
        child = getattr(test, "child", None)
        if child is None:
            return
        watcher = getattr(test, "_completionWatcher", None)
        if watcher is not None:
            return

        def _watch_for_completion():
            try:
                child.wait()
            except Exception:
                return
            self._recordCompletionSignal(test)

        watcher = threading.Thread(
            target=_watch_for_completion,
            name=f"ats-completion-{getattr(child, 'pid', 'unknown')}",
            daemon=True,
        )
        test._completionWatcher = watcher
        watcher.start()

    def _closePidfd(self, test):
        pidfd = getattr(test, "_pidfd", None)
        if pidfd is None:
            return
        try:
            os.close(pidfd)
        except OSError:
            pass
        test._pidfd = None

    def testEnded(self, test, status):
        """Do book-keeping when a job has exited;
           call noteEnd for machine-specific part.
        """
        from ats import configuration
        if MachineCore.debugClass:
            print("DEBUG MachineCore.testEnded invoked cwd= %s " % (os.getcwd()))

        globalPostrunScript_outname = test.globalPostrunScript_outname

        globalPostrunScript         = test.options.get('globalPostrunScript', None)
        # Strip quotes which are somehow added to the string in Python3
        # Otherwise we can't verify the file exists or execute it.
        globalPostrunScript = globalPostrunScript.replace('"', '')

        #verbose                     = test.options.get('verbose', False)
        verbose                     = configuration.options.debug

        if not (globalPostrunScript == "unset"):
            here = os.getcwd()
            os.chdir(test.directory)
            if os.path.exists(globalPostrunScript):
                self._executePreOrPostRunScript(globalPostrunScript, test, verbose, globalPostrunScript_outname)
            else:
                log("ATS ERROR: globalPostrunScript %s not found" % (globalPostrunScript), echo=True)
                sys.exit(-1)
            os.chdir(here)

        self.numberTestsRunning -= 1
        if MachineCore.debugClass or MachineCore.canRunNow_debugClass:
            print("DEBUG MachineCore.testEnded decreased self.numberTestsRunning by 1 to %d " % self.numberTestsRunning)

        #if num_nodes' in test.__dict__:
        #    num_nodes = test.__dict__.get('num_nodes')
        #    self.numberNodesExclusivelyUsed -= num_nodes
        #    print "MachineCore.testEnded decreased self.numberNodesExclusivelyUsed by %d to %d " % \
        #        (num_nodes, self.numberNodesExclusivelyUsed)

        if test.numNodesToUse > 0:
            self.numberNodesExclusivelyUsed -= test.numNodesToUse
            if MachineCore.debugClass or MachineCore.canRunNow_debugClass:
                print("DEBUG MachineCore.testEnded decreased self.numberNodesExclusivelyUsed by %d to %d (max is %d)" %
                      (test.numNodesToUse, self.numberNodesExclusivelyUsed, self.numNodes))

        test.set(status, test.elapsedTime())
           #note test.status is not necessarily status after this!
           #see test.expectedResult

        endNote = self.noteEnd(test)  #to be defined in children

        if endNote: # Check that there is something to be printed
            if not configuration.options.removeEndNote: # Does the user want it to be printed
                print(endNote)

        # now close the outputs
        if test.stdOutLocGet() != 'terminal':
            test.fileHandleClose()

        self.scheduler.testEnded(test)

    def kill(self, test): # override if not using subprocess
        "Kill the job running test."
        if test.child:
            test.child.kill()
            self._closePidfd(test)
            if test.stdOutLocGet() != 'terminal':
                test.fileHandleClose()

    def launch(self, test):
        """Start executable using a suitable command.
           Return True if able to do so.
           Call noteLaunch if launch succeeded."""

        from ats import configuration
        #print test.__dict__
        ##print self.__dict__

        nosrun = test.options.get('nosrun', False)
        serial = test.options.get('serial', False) # support serial=True on a per-test basis for backwards compatability for a while
        if nosrun == True or serial == True:
            test.commandList = self.calculateBasicCommandList(test)
            test.cpus_per_task = 1
        else:
            test.commandList = self.calculateCommandList(test)
            if test.commandList == None:
                log("ATS def launch returning false, commandList is None", echo=True)
                return False

        #
        # On Blueos (Sierra/Ansel) Set JSM_JSRUN_NO_WARN_OVERSUBSCRIBE the same as lrun does
        #
        if configuration.SYS_TYPE.startswith('blueos'):
            os.environ['JSM_JSRUN_NO_WARN_OVERSUBSCRIBE'] = '1'

        # To enable running of threaded codes in 1 thread mode, the OMP_NUM_THREADS must be
        # set either by the user before the run, or by the test 'nt' option, or by
        # the command line option to ATS --ompNumThreads.  If none of these are set, then
        # set it to 1.
        if configuration.options.ompNumThreads > 0:
            # Priority 1 setting, ats command line
            if configuration.options.verbose:
                print("ATS launch setting OMP_NUM_THREADS %d as user specified --ompNumThreads=%d" %
                      (configuration.options.ompNumThreads, configuration.options.ompNumThreads))
            os.environ['OMP_NUM_THREADS'] = str(configuration.options.ompNumThreads)
        else:
            # Priority 2  setting, within an ATS test line
            omp_num_threads = test.options.get('nt', -1)
            if (omp_num_threads > 0):
                if configuration.options.verbose:
                    print("ATS launch setting OMP_NUM_THREADS %d based on test 'nt'option" % omp_num_threads)
                os.environ['OMP_NUM_THREADS'] = str(omp_num_threads)
            else:
                # Priority 3 setting, the user has already set OMP_NUM_THREADS in their environment
                if 'OMP_NUM_THREADS' in os.environ:
                    if configuration.options.verbose:
                        temp_omp= os.getenv("OMP_NUM_THREADS")
                        # print "ATS detected that OMP_NUM_THREADS is already set to %s" % (temp_omp)
                # Priority 4 setting, set it to 1 if it is not othewise set
                else:
                    if configuration.options.verbose:
                        print("ATS launch setting OMP_NUM_THREADS 1 by default for as it was not specified for the test.")
                        # print "    This should allow for threaded applications to run with non threaded tests with a single thread."
                    os.environ['OMP_NUM_THREADS'] = str(1)

        # Set default KMP_AFFINITY so that OpenMP runs are OK on Toss 3
        # This is experimental for now.
        if configuration.SYS_TYPE.startswith('toss'):
            if MachineCore.printExperimentalNotice:
                MachineCore.printExperimentalNotice = False
                print("ATS Experimental: setting KMP_AFFINITY to %s on Toss" % configuration.options.kmpAffinity)
            os.environ['KMP_AFFINITY'] = configuration.options.kmpAffinity

        # Turn off shared memory mpi collective operations on toss and chaos
        if configuration.SYS_TYPE.startswith('toss'):
            os.environ['VIADEV_USE_SHMEM_COLL'] = "0"

        # LS_COLORS can mess up somesystem and is not needed for any platform by ATS
        os.environ['LS_COLORS'] = ""

        # Tell Flux to use ASCII character set, otherwise Python can't handle the output and dies with error like so:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 3942: invalid start byte
        # 
        # File ".../ats/tests.py", line 643, in recordOutput
        # for line in f:
        # File "/collab/usr/gapps/python/.../lib/python3.9/codecs.py", line 322, in decode
        #   (result, consumed) = self._buffer_decode(data, self.errors, final)
        os.environ['FLUX_F58_FORCE_ASCII'] = "1"

        # Bamboo env vars can also mess up somesystem runs by exceeding char limit for env vars
        # remove them
        os.environ['bamboo_shortJobName'] = ""
        os.environ['bamboo_capability_system_git_executable'] = ""
        os.environ['bamboo_build_working_directory'] = ""
        os.environ['bamboo_shortPlanKey'] = ""
        os.environ['bamboo_planName'] = ""
        os.environ['bamboo_capability_system_jdk_JDK_1_8_0_71'] = ""
        os.environ['bamboo_buildKey'] = ""
        os.environ['bamboo_capability_system_jdk_JDK'] = ""
        os.environ['bamboo_capability_sys_type'] = ""
        os.environ['bamboo_capability_cluster'] = ""
        os.environ['bamboo_buildFailed'] = ""
        os.environ['bamboo_buildResultKey'] = ""
        os.environ['bamboo_plan_storageTag'] = ""
        os.environ['bamboo_planKey'] = ""
        os.environ['bamboo_capability_system_builder_ant_Ant'] = ""
        os.environ['bamboo_shortPlanName'] = ""
        os.environ['bamboo_buildResultsUrl'] = ""
        os.environ['bamboo_buildPlanName'] = ""
        os.environ['bamboo_working_directory'] = ""
        os.environ['bamboo_agentWorkingDirectory'] = ""
        os.environ['bamboo_buildTimeStamp'] = ""
        os.environ['bamboo_shortJobKey'] = ""
        os.environ['bamboo_buildNumber'] = ""
        os.environ['bamboo_agentId'] = ""
        os.environ['bamboo_capability_system_jdk_JDK_1_8'] = ""
        os.environ['bamboo_resultsUrl'] = ""

        test.commandLine = " ".join(test.commandList)

        sandbox        = test.options.get('sandbox', False)
        directory      = test.options.get('directory', None)
        deck_directory = test.options.get('deck_directory', None)

        if sandbox:
            # directory is the name of the sandbox directory
            if directory == None or directory == '':
                directory = ('%s_%d_%04d_%s') % ('sandbox', os.getpid(), test.serialNumber, test.namebase)

            if deck_directory == None or deck_directory == '':
                deck_directory = os.getcwd()

            if not os.path.isdir(directory):

                if MachineCore.debugClass:
                    print("MachineCore.launch \n\tcwd=%s \n\tdir=%s \n\tdeck_directory=%s" %
                          (os.getcwd(), directory, deck_directory))

                log("ATS machines.py Creating sandbox directory : %s" % directory, echo=True)
                copytree(deck_directory, directory, ignore=ignore_patterns('*.logs', 'html', '.svn', '*sandbox*'))


        #--- placing this here doesn't allow the machines to handle the skip option themselves..
        if configuration.options.skip:
            test.set(SKIPPED, "--skip option")
            return False

        test.setStartDateTime()
        result = self._launch(test)
        if result:
            self.noteLaunch(test)

        return result

    def __results(self, key, default, results, options):
        val = results.get(key, default)
        if val == default:
            val = options.get(key, default)
        return val

    def log_prepend(self, test, outhandle):
        # Prepend information about the test to its standard output
        magic = test.options.get('magic', '#ATS:')
        results = test.getResults()

        commandLine = self.__results('commandLine', '', results, test.options)
        print("%scommandLine =%s" % (magic, commandLine), file=test.outhandle)

        if hasattr(test, 'rs_filename'):
            if os.path.isfile(test.rs_filename):
                myfile = open(test.rs_filename, mode='r', errors='ignore')
                all_of_it = myfile.read()
                myfile.close()
                print("%sjsrun_rs =\n%s" % (magic, all_of_it), file=test.outhandle)

        directory = self.__results('directory', '', results, test.options)
        print("%sdirectory =%s" % (magic, directory), file=test.outhandle)

        executable = self.__results('executable', '', results, test.options)
        print("%sexecutable =%s" % (magic, executable), file=test.outhandle)

        name = self.__results('name', '', results, test.options)
        print("%sname =%s" % (magic, name), file=test.outhandle)

        clas = self.__results('clas', '', results, test.options)
        print("%sclas =%s" % (magic, clas), file=test.outhandle)

        np = self.__results('np', 1, results, test.options)
        print("%snp =%s" % (magic, np), file=test.outhandle)

        script = self.__results('script', '', results, test.options)
        print("%sscript =%s" % (magic, script), file=test.outhandle)

        testpath = self.__results('testpath', '', results, test.options)
        print("%stestpath =%s\n" % (magic, testpath), file=test.outhandle)

        test.outhandle.flush()
        os.fsync(test.outhandle.fileno())

    def _launch(self, test):
        """Replace if not using subprocess (unusual).
The subprocess part of launch. Also the part that might fail.
"""
        if MachineCore.debugClass:
            print("DEBUG MachineCore._launch invoked cwd= %s " % os.getcwd())
            #print self
            #print test
            #print test.options
            #print test.__dict__
            #print self.__dict__


        from ats import configuration
        # See if user specified a file to use as stdin to the test problem.
        stdin_file                 = test.options.get('stdin', None)
        globalPrerunScript_outname = test.globalPrerunScript_outname

        globalPrerunScript          = test.options.get('globalPrerunScript', None)
        # Strip quotes which are somehow added to the string in Python3
        # Otherwise we can't verify the file exists or execute it.
        globalPrerunScript = globalPrerunScript.replace('"', '')

        #verbose                     = test.options.get('verbose', False)
        verbose                     = configuration.options.debug


        if not (globalPrerunScript == "unset"):
            here = os.getcwd()
            os.chdir(test.directory)
            if os.path.exists(globalPrerunScript):
                self._executePreOrPostRunScript(globalPrerunScript, test, verbose, globalPrerunScript_outname)
            else:
                log("ATS ERROR: globalPrerunScript %s not found" % (globalPrerunScript), echo=True)
                sys.exit(-1)
            os.chdir(here)

        try:
            Eadd    = test.options.get('env', None)
            if Eadd is None:
                E = None
            else:
                # This is old Paul DuBois coding, with ugly syntax.
                #
                # That is the syntax for the user within a 'test' or #ATS line is:
                # env={'ANIMAL': 'duck', 'CITY': 'Seattle', 'PLANET': 'Venus'}
                #
                # The apparent reason for this ugliness, is that is how the environment
                # object is stored in Python.  So it amakes the coding easier
                # here, but it shifts the burden to the user to get that syntax correct,
                # including the brackets, quotes, commans, and colons.
                #
                # Will live with this for now, but would really like this to be more human friendly
                #
                # env="ANIMAL=duck, CITY=Seattle, PLANET=Venus"
                #
                if MachineCore.debugClass:
                    print("DEBUG MachineCore._launch env specified =  %s " % Eadd)
                E = os.environ.copy()
                E.update(Eadd)

            testStdout = test.stdOutLocGet()

            if stdin_file is None:
                #print "DEBUG MachineCore._launch 010 "
                testStdin = None
            else:
                #print "DEBUG MachineCore._launch 020 "
                testStdin = open(test.directory + '/' + stdin_file, errors='replace')

            # 2016-09-01
            # Starting jobs too fast confuses slurm and MPI.  Short wait between each job submittal
            # This showsd up with my atsHello test program
            # Default sleep is 1 on toss, 0 on other systems, may be set by user on command line
            #
            # 2016-12-02
            # Default sleep is now 0 on all systems.

            # 2021-Sep-21
            # Per project request.  If nosrun is on, do not sleep (as we are not using MPI in that scenario)
            #
            nosrun  = test.options.get('nosrun', False)
            if nosrun == False:
                if configuration.options.sleepBeforeRun > 0.0:
                    if MachineCore.printSleepBeforeSrunNotice:
                        MachineCore.printSleepBeforeSrunNotice = False
                        print("ATS Info: MachineCore._launch Will sleep %f seconds before each srun " % configuration.options.sleepBeforeRun)
                    time.sleep(configuration.options.sleepBeforeRun)


            if testStdout == 'file':
                # Get the file handles for standard out and standard error
                outhandle, errhandle = test.fileHandleGet()

                # Prepend information about the test to its standard output
                self.log_prepend(test, test.outhandle)

                if stdin_file is None:
                #print "DEBUG MachineCore._launch %s " % test.commandList
                #print E
                #test.child = subprocess.Popen(test.commandList, cwd=test.directory, stdout=outhandle, stderr=errhandle, env=E, text=True)
                    test.child = subprocess.Popen(test.commandList, universal_newlines=True, cwd=test.directory, stdout=outhandle, stderr=errhandle, env=E, text=True)
                    #test.child.wait()
                else:
                    test.child = subprocess.Popen(test.commandList, cwd=test.directory, stdout = outhandle, stderr = errhandle, env=E, stdin=testStdin, text=True)

            elif testStdout == 'terminal':
                if MachineCore.debugClass:
                    print("DEBUG MachineCore._launch Invoking Popen 2 %s " % test.commandList)


                if stdin_file is None:
                    test.child = subprocess.Popen(test.commandList, cwd=test.directory, env=E, text=True)
                else:
                    test.child = subprocess.Popen(test.commandList, cwd=test.directory, env=E, stdin=testStdin, text=True)

            elif testStdout == 'both':
                # Get the file handles for standard out and standard error
                outhandle, errhandle = test.fileHandleGet()

                # Prepend information about the test to its standard output
                self.log_prepend(test, test.outhandle)

                if MachineCore.debugClass:
                    print("DEBUG MachineCore._launch Invoking Popen 3 %s " % test.commandList)

                if stdin_file is None:
                    test.child = subprocess.Popen(test.commandList, cwd=test.directory, stdout = subprocess.PIPE, stderr=subprocess.STDOUT, env=E, text=True)
                else:
                    test.child = subprocess.Popen(test.commandList, cwd=test.directory, stdout = subprocess.PIPE, stderr=subprocess.STDOUT, env=E, stdin=testStdin)

            self._ensurePidfd(test)
            test.set(RUNNING, test.commandLine)

            self.running.append(test)
            self.numberTestsRunning += 1
            if MachineCore.debugClass or MachineCore.canRunNow_debugClass:
                print("DEBUG MachineCore.testEnded increased self.numberTestsRunning by 1 to %d " % self.numberTestsRunning)

            if test.numNodesToUse > 0:
                self.numberNodesExclusivelyUsed += test.numNodesToUse
                if MachineCore.debugClass or MachineCore.canRunNow_debugClass:
                    print("DEBUG MachineCore._launch__ increased self.numberNodesExclusivelyUsed by %d to %d (max is %d)" %
                          (test.numNodesToUse, self.numberNodesExclusivelyUsed, self.numNodes))

            return True

        except OSError as e:
            if test.stdOutLocGet() != 'terminal':
                test.fileHandleClose()

            test.set(FAILED, str(e))
            return False

    def startRun(self, test):
        """For interactive test object, launch the test object.
           Return True if able to start the test.
        """
        if MachineCore.debugClass:
            print("DEBUG MachineCore.startRun invoked")
        self.runOrder += 1
        test.runOrder = self.runOrder
        return self.launch(test)

    def _execute(self, cmd_line, verbose=False, file_name=None, exit=True):
        """
        Function to run a command and display output to screen.
        """

        if file_name is not None:
            execute_ofp = open(file_name, 'w')

        process = subprocess.Popen(cmd_line, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # Poll process for new output until finished
        while True:
            nextline = process.stdout.readline()
            if (nextline == '' and process.poll() != None):
                break
            if (verbose == True):
                sys.stdout.write(nextline)
                # sys.stdout.flush()
            if file_name is not None:
                execute_ofp.write(nextline)

        output = process.communicate()[0]
        exitCode = process.returncode

        if file_name is not None:
            execute_ofp.close()

        if (exitCode == 0):
            pass
        else:
            if exit:
                log('%s FATAL RETURN CODE %d Command: %s' % ("ATS", exitCode, cmd_line), echo=True)
                raise SystemExit(1)

        return exitCode

    def _executePreOrPostRunScript(self, cmd_line, test, verbose=False, file_name=None, exit=True):
        """
        Function to run a command and display output to screen.  The test dictionary is passed in as a string
        """

        #print "AMBYR"
        #for key in test.__dict__:
        #   print "test key ", key, " is ", test.__dict__[key]
        #print "ONDRE"

        my_executable  = str(test.__dict__["executable"])
        my_commandLine = str(test.__dict__["commandLine"])
        my_np = str(test.__dict__["np"])
        my_outname = str(test.__dict__["outname"])
        my_directory = str(test.__dict__["directory"])

        if file_name is not None:
            execute_ofp = open(file_name, 'w')

        process = subprocess.Popen(cmd_line + \
            " " + '"' + my_executable + '"' + \
            " " + '"' + my_np + '"' + \
            " " + '"' + my_directory + '"' + \
            " " + '"' + my_outname + '"' + \
            " " + '"' + my_commandLine + '"', \
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # Poll process for new output until finished
        while True:
            nextline = process.stdout.readline()
            if (nextline == '' and process.poll() != None):
                break
            if (verbose == True):
                sys.stdout.write(nextline)
                # sys.stdout.flush()
            if file_name is not None:
                execute_ofp.write(nextline)

        output = process.communicate()[0]
        exitCode = process.returncode

        if file_name is not None:
            execute_ofp.close()

        if (exitCode == 0):
            pass
        else:
            if exit:
                log('%s FATAL RETURN CODE %d Command: %s' % ("ATS", exitCode, cmd_line), echo=True)
                raise SystemExit(1)

        return exitCode



#### end of MachineCore

#-----------------------------------------------------------
# class Machine
#-----------------------------------------------------------
class Machine (MachineCore):
    """Class intended for override by specific machine environments.
Some methods are possible overrides.
Usually the parent version should be called too.
To call the parent version of foo: super(YourClass, self).foo(args)
However, the most important methods have a "basic" verison you can just call.
You can call your class anything, just put the correct comment line at
the top of your machine. See documentation for porting.
"""
    def __init__(self, name, npMaxH):
        """Be sure to call this from child if overridden

Initialize this machine. npMax supplied by __init__, hardware limit.
If npMax is negative, may be overridden by command line. If positive,
is hard upper limit.
"""

        # print "DEBUG Machine:MachineCore %s %d" % (name, npMaxH)

        self.name = name
        self.numberTestsRunning = 0
        self.numberNodesExclusivelyUsed = 0
        self.numberTestsRunningMax = max(1, abs(npMaxH))
        self.numNodes = -1
        self.npMaxH = npMaxH    # allow the machine modules to access this value
        self.hardLimit = (npMaxH > 0)
        self.naptime = 0.2 #number of seconds to sleep between checks on running tests.
        self.running = []
        self._completionEvent = threading.Event()
        self._completionQueue = deque()
        self._completionQueueIds = set()
        self._completionQueueLock = threading.Lock()
        self._completionStats = {}
        self._completionStatsLock = threading.Lock()
        self._completion_span_hooks = []
        self._completion_queue_snapshot_hooks = []
        self.runOrder = 0
        from ats import schedulers
        self.scheduler = schedulers.StandardScheduler()
        self.init()


    def init(self):
        "Override to add any needed initialization."
        pass

    def addOptions(self, parser):
        "Override to add  options needed on this machine."
        pass

    def examineOptions(self, options):
        """Examine options from command line, possibly override command line choices.
           Always call examineBasicOptions
        """
        self.examineBasicOptions(options)


    def calculateCommandList(self, test):
        """Prepare for run of executable using a suitable command.
If overriding, get the vanilla one from ``calculateBasicCommand``,
then modify if necessary.
        """
        return self.calculateBasicCommandList(test)

    def periodicReport(self):
        "Make the machine-specific part of periodic report to the terminal."
        terminal(len(self.running), "tests running on", self.numberTestsRunning,
                 "of", self.numberTestsRunningMax, "processors.")

    def canRun(self, test):
        """
A child will almost always replace this method.

Is this machine able to run the test interactively when resources become
available?  If so return ''.

Otherwise return the reason it cannot be run here.
"""
        if test.np > 1:   #generic machine sequential only
            return "Too many processors needed (%d)" % test.np
        return ''

    def canRunNow(self, test):
        """
A child will almost replace this method. No need to call parent version.

Is this machine able to run this test now? Return True/False.
If True is returned, an attempt will be made to launch. noteLaunch will be
called if this succeeds.
"""
        return self.numberTestsRunning  + 1 <= self.numberTestsRunningMax

    def noteLaunch(self, test):
        """
A child will almost replace this method. No need to call parent version.

test has been launched. Do your bookkeeping. numberTestsRunning has already
been incremented.
"""
        pass

    def noteEnd(self, test):
        """
A child will almost replace this method. No need to call parent version.

test has finished running. Do any bookkeeping you need. numberTestsRunning has
already been decremented.
"""
        pass

    def quit(self):
        """
A child might replace this method. No need to call parent version.
Final cleanup if any.
        """
        pass





    def getResults(self):
        """
A child might replace this to put more information in the results,
but probaby wants to call the parent and then update the
dictionary this method returns.

Return dict of machine-specific facts for manager postprocessing state.
Include results from the scheduler.
"""
        result = {}
        result.update(self.scheduler.getResults())
        result.update({
            "name": self.name,
            "numberTestsRunningMax": self.numberTestsRunningMax,
            "hardLimit": self.hardLimit,
            "naptime": self.naptime
        })
        return result

#-----------------------------------------------------------
# class BatchFacility
#-----------------------------------------------------------
class BatchFacility(object):
    """Interface to a batchmachine"""
    def init(self):
        pass

    def getResults(self):
        "Return machine-specific facts for manager postprocessing state."
        return {"name": self.label()}

    def label(self):
        "Return a name for this facility."
        return ''

    def addOptions(self, parser):
        "Add batch options to command line (see optparser)"
        pass

    def examineOptions(self, options):
        "Examine the options."
        pass

    def load(self, testlist):
        "Execute these tests"
        return

    def quit(self):
        "Called when ats is done."
        pass


#-----------------------------------------------------------
# class BatchSimulator
#-----------------------------------------------------------
class BatchSimulator(BatchFacility):
    """
A fake batch you can use for debugging input by setting::

    BATCH_TYPE=batchsimulator

"""
    def label(self):
        return "BatchSimulator"

    def __init__(self, name, npMaxH):
        self.name = name
        self.npMaxH = npMaxH
        self.np = npMaxH

    def load(self, batchlist):
        "Simulate the batch system"
        log("Simulation of batch load:", echo=True)
        for t in batchlist:
            log(t, echo=True)
