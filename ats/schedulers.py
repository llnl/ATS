"""Defines standard scheduler for interactive jobs."""
from itertools import chain
import time
from ats.atsut import debug, CREATED, EXPECTED, PASSED, RUNNING
from ats.log import AtsLog, log

def comparePriorities (t1, t2):
    "Input is two tests or groups; return comparison based on totalPriority."
    return t2.totalPriority - t1.totalPriority

class StandardScheduler (object):
    """A (replaceable) object that schedules interactive jobs to the machine under the direction
    of the manager. Handles issues such as groups, waits, priorities. The machine.scheduler
    is an instance of the desired scheduler. User can replace this with their own
    policies.
    """
    name = "Standard Scheduler"
    # Dictionary of block (directory) => group number
    # indicating which groups are currently blocking which directories
    blocks = {}

    def prioritize(self, interactiveTests):
        """Give each test a final totalPriority.  onCollected routines may change."""
# have to delay looking at the machine / configuration to avoid import race
        global machine, configuration
        from ats import configuration
        machine = configuration.machine
        self.verbose = configuration.options.verbose or debug() or \
                       configuration.options.skip
        self.schedule = AtsLog(directory=log.directory,
                               name='atss.log',
                               logging=configuration.options.logUsage,
                               echo=False)
        self.calculatePriority(interactiveTests)

    def calculatePriority(self, interactiveTests):
        for t in interactiveTests:
            waitOnMe = [x for x in interactiveTests if t in x.waitUntil]
            t.totalPriority += sum([w.priority for w in waitOnMe])

    def load(self, interactiveTests):
        """Initialize scheduler with a list of interactive tests to run from manager """
#
        self.blocking = []
        self.groups = []
        for t in interactiveTests:
            if t.group not in self.groups:
                self.groups.append(t.group)
                t.group.totalPriority = t.totalPriority
            else:
                t.group.totalPriority = max(t.group.totalPriority, t.totalPriority)
        self.groups.sort()
        # self.groups.sort(comparePriorities)

        self.schedule("   Total", "    Test", "Serial", " Group", "Test")
        self.schedule("Priority", "Priority", "Number", "Number", "Name")
        for t in chain(*self.groups):
            msg = "%8d %8d %6d %6d %s" % \
                  (t.totalPriority, t.priority, t.serialNumber, t.group.number, t.name)
            self.schedule(msg)
        return len(self.groups) > 0

    def addInteractiveTests(self, interactiveTests):
        """Add newly-discovered interactive tests after the scheduler is loaded.

        Args:
            interactiveTests (iterable): ATS tests discovered after the initial
                ``load`` call.  ``AtsManager.core(stream=True)`` calls this on
                the main thread as completed definitions are published.

        Returns:
            bool: ``True`` when at least one test was added; ``False`` when the
            input iterable was empty.
        """
        interactiveTests = list(interactiveTests)
        if not interactiveTests:
            return False
        self.calculatePriority(interactiveTests)
        for t in interactiveTests:
            if t.group not in self.groups:
                self.groups.append(t.group)
                t.group.totalPriority = t.totalPriority
            else:
                t.group.totalPriority = max(t.group.totalPriority, t.totalPriority)
        self.groups.sort()

        for t in interactiveTests:
            msg = "%8d %8d %6d %6d %s" % \
                  (t.totalPriority, t.priority, t.serialNumber, t.group.number, t.name)
            self.schedule(msg)
        return True

    def testlist(self):
        """Return the list of tests in groups that have not yet completed."""
        return chain(*self.groups)

    def step(self):
        """Do one step of the loop, checking for tests that have finished and
           starting new ones. Return True until all tests done.
        """
        machine.checkRunning()
        if machine.remainingCapacity() == 0:
            return True

        # It is possible that a job can be started. Try to do so.
        # Note that this is not certain; for example, all waiting jobs have np = 2 but only one
        # processor available, so nothing is eligible.
        nextTest = self.findNextTest()
        while nextTest is not None:
            if debug():
                self.schedule("Chose #%d to start." % nextTest.serialNumber)
            self.addBlock(nextTest)
            result = machine.startRun(nextTest)
            if not configuration.options.removeStartNote:
                self.logStart(nextTest, result)
            if not result:
                self.removeBlock(nextTest)
                break   # failure to launch, let it come back if tests left.
            nextTest = self.findNextTest()

        # find out if we need to be called again, as cheaply as possible.
        if machine.numberTestsRunning > 0:
            return True
        for t in chain(*self.groups):
            if t.status is CREATED:
                return True
        else:
            return False

    def isWaiting(self, test):
        "is test forced to wait for another?"
        #print "DEBUG isWaiting invoked"
        for t in test.waitUntil:
            if t.status in (CREATED, RUNNING):
                #print "DEBUG isWaiting return True"
                return True
        #print "DEBUG isWaiting return False"
        return False

    def isBlocked(self, test):
        "is test prevented from running right now due to group/directory issues?"
        #print "DEBUG isBlocked invoked"
        d = test.block
        if not d:
            #print "DEBUG isBlocked returning False 100"
            return False
        # check if the directory is blocked
        if d in self.blocks:
            # check if another group is blocking
            if test.group.number != self.blocks[d]:
                return True
        return False

    def addBlock(self, test):
        "Block directories, if any, needed for test and its group."
        g = test.group
        if g.isBlocking:
            return
        for t in g:
            if t.independent:
                continue
            d = t.block
            if d:
                # If any test in the group blocks, add the block (directory)
                # to the blocking list and mark this group as blocking.
                g.isBlocking = True
                self.blocks[d] = g.number
        if g.isBlocking:
            if debug():
                self.schedule("Add blocks", g.number)

    def removeBlock(self, test):
        "Check and possibly remove the block on the group of this test."
        g = test.group
        if not g.isBlocking:
            return

        for t in g:
            if t.independent:
                continue
            if t.status in  (CREATED, RUNNING):
                return
        else:
            # Once the group is complete, remove the blocks (directories)
            # from the blocking list and unmark this group as blocking.
            g.isBlocking = False
            for t in g:
                if t.independent:
                    continue
                d = t.block
                if d:
                    if d in self.blocks:
                        del self.blocks[d]
            self.schedule("Removed block", g.number)

    def isEligible(self, test):
        """Is test eligible to start now?
        """
        #print "DEBUG isEligible invoked"
        return machine.canRunNow(test) and \
               (not self.isBlocked(test))  and \
               (not self.isWaiting(test))

    def findNextTest(self):
        """Return the next test to run, or None if none can be run now.
           Called by step
           Calls isEligible to check for resource conflicts with running tests.
           machine's canRunNow used to check hardware availability.
        """
        #print "DEBUG findNextTest invoked"
        if machine.remainingCapacity() == 0:
            #print "DEBUG findNextTest 100 return None"
            return None

        for t in chain(*self.groups):
            if t.status is not CREATED:
                continue
            if self.isEligible(t):
                #print "DEBUG findNextTest 300 return t"
                return t
        else:
            self.reportObstacles()
            #print "DEBUG findNextTest 500 return None"
            return None

    def logStart(self, test, result):
        "Make appropriate log entries about the test that was started"
        if result:
            m1 = "Start"
        elif configuration.options.skip:
            m1 = "SKIP "
        else:
            m1 = ""
            if self.verbose or debug():
                m1 = "Failed attempting to start"
        n = len(test.group)
        my_nn = 0
        my_nt = 0
        my_ngpu = 0
        msgHosts=""
        if hasattr(test, 'rs_nodesToUse'):
            if len(test.rs_nodesToUse) > 0:
                msgHosts = "Hosts = [ "
                for host in test.rs_nodesToUse:
                    msgHosts += str(host) + " "
                msgHosts += "]"
        if hasattr(test, 'num_nodes'):
            my_nn = test.num_nodes
        if hasattr(test, 'nt'):
            my_nt = test.nt
        if hasattr(test, 'ngpu'):
            my_ngpu = test.ngpu

        if n == 1:
            if (test.srunRelativeNode >= 0):
                msg = '%s #%4d r=%d, N=%d-%d, np=%s, %s, %s' % \
                  (m1, test.serialNumber, test.srunRelativeNode, test.numberOfNodesNeeded, test.numNodesToUse, test.np, time.asctime(), test.name)
            else:
                # msg = '%s #%4d %s, %s nn=%i, np=%i, nt=%i, ngpu=%i %s (remaining capacity=%i)' % \
                #   (m1, test.serialNumber, test.name, msgHosts, my_nn, test.np, my_nt, my_ngpu, time.asctime(), machine.remainingCapacity())
                msg = '%s #%4d %s, %s nn=%i, np=%i, nt=%i, ngpu=%i %s ' % \
                  (m1, test.serialNumber, test.name, msgHosts, my_nn, test.np, my_nt, my_ngpu, time.asctime())
        else:
            if (test.srunRelativeNode >= 0):
                msg = '%s #%4d r=%d, N=%d-%d, np=%s, %s, (Group %d #%d) %s' % \
                  (m1, test.serialNumber, test.srunRelativeNode, test.numberOfNodesNeeded, test.numNodesToUse, test.np, test.groupNumber, time.asctime(), test.groupSerialNumber, test.name)
            else:
                msg = '%s #%4d (Group %d #%d) %s, %s nn=%i, np=%i, nt=%i, ngpu=%i %s' % \
                  (m1, test.serialNumber, test.groupNumber, test.groupSerialNumber, test.name, msgHosts, my_nn, test.np, my_nt, my_ngpu, time.asctime())

        if configuration.options.showGroupStartOnly:
            echo = (not result) or self.verbose or (test.groupSerialNumber == 1) or test.options.get('record', False)
        else:
            echo = (result) or self.verbose or test.options.get('record', False)
        log(msg, echo=echo)
        self.schedule(msg)
        if self.verbose or debug():
            log.indent()
            log("Executing", test.commandLine)
            log("in directory", test.directory)
            #log("with timelimit", test.timelimit)
            log.dedent()

    def testEnded(self, test):
        """Manage scheduling and reporting tasks for a test that ended.
Log result for every test but only show certain ones on the terminal.
Prune group list if a group is finished.
"""
        echo = self.verbose or (test.status not in (PASSED, EXPECTED))
        g = test.group
        n = len(g)
        if n == 1:
            msg = "%5s #%4d %s %s"  % \
                (test.status, test.serialNumber, test.name, test.message)
        else:
            msg = "%s #%d %s %s Group %d #%d of %d" %  \
                (test.status, test.serialNumber, test.name, test.message,
                 g.number, test.groupSerialNumber, n)
        log(msg, echo = echo)
        self.schedule(msg, time.asctime())
        self.removeBlock(test)
        if g.isFinished():
            g.recordOutput()
            self.groups.remove(g)

    def periodicReport(self):
        """Do the scheduler and machine parts of the periodic Report."""
        glist = [g for g in self.groups if not g.isFinished()]
        tleft = [t for t in chain(*glist) if t.status in (CREATED, RUNNING)]
        self.schedule("Remaining:", len(glist), "groups,", len(tleft), 'tests.',
                     echo = True)
        machine.periodicReport()

    def reportObstacles(self, echo = False):
        "Report on status of tests that can't run now."
        s = self.schedule
        if machine.remainingCapacity() == 0:
            return
        if (not machine.numberTestsRunning) or debug():
            tc = [t for t in chain(*self.groups) if t.status is CREATED and \
                 ((not machine.canRunNow(t)) or self.isBlocked(t) or self.isWaiting(t))]
            if not tc:
                return
            s("------------------------------------------------", echo=echo)
            s("Jobs ready to run but not able to due to wait, block, or cpu", echo=echo)
            s("Serial", "tPriority", "Priority", "Group", "W", "B","C", "Name", echo=echo)
            for t in tc:
                s("%6d %9d %8d %5d %1d %1d %1d %s" % \
                   (t.serialNumber, t.totalPriority, t.priority, t.groupNumber,
                    self.isWaiting(t),
                    self.isBlocked(t), not machine.canRunNow(t), t.name), echo=echo)
            s(" ",echo=echo)
        elif self.verbose:
            tc = [t for t in chain(*self.groups) if t.status is CREATED and \
                 self.isBlocked(t) and (not self.isWaiting(t))]
            if not tc:
                return
            s("------------------------------------------------", echo=echo)
            s("Jobs ready to run but not able due to block or cpu", echo=echo)
            s("Serial", "tPriority", "Priority", "Group", "B","C", "Name", echo=echo)
            for t in tc:
                s("%6d %9d %8d %5d %1d %1d %s" % \
                   (t.serialNumber, t.totalPriority, t.priority, t.groupNumber,
                   self.isBlocked(t), not machine.canRunNow(t), t.name), echo=echo)

    def getResults(self):
        """Results for the atsr file."""
        return {"scheduler": self.name}
