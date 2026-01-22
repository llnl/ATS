import os
import re
import time
from ats import configuration
from ats.log import log
from ats.atsut import INVALID, PASSED, FAILED, SKIPPED, BATCHED, RUNNING,\
                  CREATED, FILTERED, TIMEDOUT, HALTED, EXPECTED, \
                  is_valid_file, debug, AtsError, abspath

from ats.times import hms, curDateTime, Duration
from ats.executables import Executable

class AtsTestGroup(list):
    "A group of tests."
    def __init__(self, number):
        self.number = number
        self.isBlocking = False

    def __hash__(self):
        return hash(self.number)

    def __ge__(self, other):
        return self.number >= other.number

    def __gt__(self, other):
        return self.number > other.number

    def __le__(self, other):
        return self.number <= other.number

    def __lt__(self, other):
        return self.number < other.number

    def __eq__(self, other):
        return self.number == other.number

    def __ne__(self, other):
        return self.number != other.number

    def isFinished(self):
        "Any left to run?"
        for t in self:
            if t.status in (CREATED, RUNNING):
                return False
        return True

    def hasFailed(self):
        "Assuming isFinished, did anything fail?"
        for t in self:
            if t.status in (FAILED, HALTED, TIMEDOUT):
                return True
        return False

    def echoStatus(self):
        "Anything funny going on?"
        for t in self:
            if t.status not in (PASSED, EXPECTED, FILTERED, SKIPPED):
                return True
        return False

    def recordOutput(self):
        "Driver for test.recordOutput over this group."
        groupFailure = self.hasFailed()
        for t in self:
            t.recordOutput(groupFailure)

def serialNumberSort(t1, t2):
    return t1.serialNumber - t2.serialNumber

# This class is not directly exposed to the public
# Instances of it are created by the manager functions test, testif
# or by user subclassing.

class AtsTest (object):
    "One test script to run, and how to run it."
    stuck = {} # test options that pertain to any new instance, file persistant
    glued = {} # test options that pertain to any new instance, persistant.
    tacked = {} # test options that pertain to any new instance, and which
                # pertain to instances created before end of current source.
    grouped = {} # test options that apply within the current group only.
    serialNumber = 0 #counter
    waitUntil = [] # list of tests that must be disposed of first
    waitUntilAccumulatorStack = []
    waitUntilAccumulator = []
    group = None
    groupCounter = 0

    def setName(self, name):
        """Set the name of this test.
           Set namebase to a version without special chars or blanks.
        """
        self.name = name
        self.namebase = re.sub('\W', '_', name)
        #print "DEBUG setName = %s\n" % self.name

    def __init__ (self, *fixedargs, **options):
        "Must not throw an exception -- object must always get created."
        super(AtsTest, self).__init__()
        AtsTest.serialNumber += 1
        AtsTest.waitUntilAccumulator.append(self)
# populate attributes
        self.serialNumber = AtsTest.serialNumber
        if AtsTest.group is None:
            AtsTest.groupCounter += 1
            self.group = AtsTestGroup(AtsTest.groupCounter)
        else:
            self.group = AtsTest.group
        self.group.append(self)
        self.groupNumber = self.group.number
        self.groupSerialNumber = len(self.group)
        self.waitUntil = AtsTest.waitUntil  #never modify this, it may be shared.
        self.runOrder = 0  # to aid in diagnosis of wait, priority
        self.depends_on = None
        self.dependents = []
        self.expectedResult = PASSED
        self.setName("uninitialized")
        self.set(INVALID, "New test, unitialized")
        self.srunRelativeNode = -1
        self.numNodesToUse = -1
        self.priority = -1
        self.totalPriority = -1
        self.startDateTime = curDateTime()
        self.endDateTime = curDateTime()
        self.output = []  #magic output, newlines and magic removed.
        self.notes = []  #note from the run
        self.block = ''
# these will all get changed below but want them set to something for getResults
        self.level = 0
        self.independent = False
        self.np = 1
        self.priority = 1
        self.totalPriority = 1
        self.directory = ''
        self.batch = False
        self.clas = ''

        self.combineOutput = False
        self.outname = ''
        self.shortoutname = ''
        self.errname = ''
        self.outhandle = None
        self.errhandle = None

        self.commandList = ['not run']
# this is just used for documentation
        self.commandLine = 'not run'

        rootdict = dict(ATSROOT = configuration.ATSROOT)

# Combine the options: first the defaults, then the glued, then the tacked,
# then the stuck, then the test options.
        self.options = {
            "script": '',
            "clas": [],
            "executable": '',
            "directory": '',
        }
        try:
            self.options.update(configuration.options.testDefaults)
            self.options.update(AtsTest.glued)
            self.options.update(AtsTest.tacked)
            self.options.update(AtsTest.stuck)
            self.options.update(AtsTest.grouped)
            self.options.update(options)
        except Exception as e:
            self.set(INVALID, 'Bad options: ' + e)
            return

        self.level = self.options['level']
        self.np = self.options['np']
        self.priority = self.options.get('priority', max(1, self.np))
        self.totalPriority = self.priority

        self.testStdout = self.options['testStdout']
        outOpts = ['file', 'terminal', 'both']
        if not self.testStdout in outOpts:
            msg = 'Invalid setting for option testStdout: ' + self.testStdout
            raise AtsError(msg)


        if configuration.options.allInteractive:
            self.batch = False
        else:
            self.batch = self.options['batch']


        if configuration.options.combineOutErr:
            self.combineOutput = True
        else:
            self.combineOutput = False

        # process the arguments
        # Note: old interface was script, clas='', **options
        # Now allow for possibility of no script, or clas as unnamed second
        # positional
        lc = len(fixedargs)
        if lc > 2:
            self.set(INVALID, 'Too many positional arguments to test command.')
            return
        elif lc == 2:
            self.options['script'] = fixedargs[0]
            self.options['clas'] = fixedargs[1]
        elif lc == 1:
            self.options['script'] = fixedargs[0]
        script = self.options['script']
        clas = self.options['clas']
        if isinstance(clas, str):
            clas = configuration.machine.split(clas)
        self.clas = [c % self.options for c in clas]
        executable = str(self.options.get('executable'))
        self.directory = self.options['directory']

        if executable == '1':
            if not script:
                self.set(INVALID, "executable = 1 requires a first argument.")
                return

            script = script.replace('$ATSROOT', configuration.ATSROOT)
            if len(configuration.ATSROOT)==0:
                script = script[1:]           # remove leading "/" or "\"
            script = script % rootdict
            self.executable = Executable(script)
            if self.directory == '':
                self.directory = os.getcwd()
            path = self.executable.path
            _, filename = os.path.split(path)
        else:
            if executable:
                executable = executable.replace('$ATSROOT', configuration.ATSROOT)
                self.executable = Executable(executable % rootdict)
            else:
                self.executable = configuration.defaultExecutable

            if script:
                script = abspath(script) % self.options
                self.clas.insert(0, script)
                if self.directory == '':
                    self.directory, filename = os.path.split(script)
            else:
                if self.directory == '':
                    self.directory = os.getcwd()
                _, filename = os.path.split(self.executable.path)

        name, _ = os.path.splitext(filename)
        self.setName(self.options.get('name', name))
        label = self.options.get('label', '')
        if label:
            label = str(label).strip()
            self.setName(self.name +  '(' + label + ')')

        if debug():
            log("Results of parsing test arguments", echo=False)
            log.indent()
            log("Name:", self.name, echo=False)
            log("Options:", echo=False)
            log.indent()
            for k in self.options:
                log(k, ": ", self.options[k], echo=False)
            log.dedent()
            log("Executable path:", self.executable.path, echo=False)
            log("Directory:", self.directory, echo=False)
            log.dedent()

        self.independent = self.options.get('independent', False)
        if not self.independent:
            # the lower() is due to peculiarities on at least the Mac
            # where os.chdir() seems to change case partially.
            self.block = self.directory.lower()

        if not self.executable.is_valid():
            self.set(INVALID, 'Executable "%s" not valid.' % self.executable)
            return

        if not os.path.isdir(self.directory):
            self.set(INVALID, 'Directory not valid: %s' % self.directory)

        if script and not is_valid_file(script):
            self.set(INVALID, "Script %s does not exist."%script)
            return

        self.fileOutNamesSet()

        #set the timelimit
        try:
            tl = options.get('timelimit', None)
            if tl is None or configuration.cuttime is not None:
                self.timelimit = configuration.timelimit
            else:
                self.timelimit = Duration(tl)
        except AtsError as msg:
            self.set(INVALID, msg)
            return

        if self.priority <= 0:
            self.set(SKIPPED, 'Test has priority <= zero.')
            return

        # if the test ends up BATCHED, such jobs are legal.

        if self.batch and configuration.options.nobatch:
            self.set(SKIPPED, "Batch not available")

        elif self.batch:
            problem = configuration.batchmachine.canRun(self)
            if not problem:
                if configuration.options.skip:
                    self.set(SKIPPED, "BACH skipped due to skip flag")
                else:
                    self.set(BATCHED, "Ready to run in batch.")
            else:
                self.set(SKIPPED, problem)

        else:
            problem = configuration.machine.canRun(self)
            if not problem:
                self.set(CREATED, "Ready to run interactively.")
            elif configuration.options.allInteractive or \
               configuration.options.nobatch or \
               self.groupNumber:
                self.set(SKIPPED, problem)
            else:
                self.set(BATCHED, problem)
                self.notes.append(\
                    "Changed to batch since unable to run interactively on this machine.")

    def __hash__(self):
        return hash(self.serialNumber)

    def __ge__(self, other):
        return self.totalPriority >= other.totalPriority

    def __gt__(self, other):
        return self.totalPriority > other.totalPriority

    def __le__(self, other):
        return self.totalPriority <= other.totalPriority

    def __lt__(self, other):
        return self.totalPriority < other.totalPriority

    def __eq__(self, other):
        return self.serialNumber == other.serialNumber

    def __ne__(self, other):
        return self.serialNumber != other.serialNumber

    def __invert__ (self):
        """Responds to the ~ operator by setting the expected status FAILED,
           returning this test object. Note unusual alteration of an operand.
           This lets us specify that a test should fail.
        """
        self.expectedResult = FAILED
        return self

    def addDependent(self, d):
        "Add a dependent test to this one."
        if self.status is FILTERED:
            d.set(FILTERED, "depends on %s that has been filtered out." % self.name)
        elif self.status is SKIPPED:
            d.set(SKIPPED, "Ancestor %s status is %s" %(self.name, self.status))
        elif self.expectedResult is not PASSED:
            d.set(SKIPPED,
                  "depends on %s that is not expected to pass." % self.name)
        elif self.status is BATCHED:
            d.set(BATCHED, "Child of batch job must be batch also.")

        if self.depends_on is not None:
            self.depends_on.addDependent(d)
        self.dependents.append(d)
        d.depends_on = self

    def getResults(self):
        "Return a dictionary containing the essential information about this test."
        if not hasattr(self, 'timelimit'):
            self.timelimit = None
        if self.depends_on is None:
            ds = 0
        else:
            ds = self.depends_on.serialNumber

        if self.output:
            out = ['Captured output, see log.']
        else:
            out = []

        # various integers are used to reconstruct the test/group relationships
        # See the coding in management.py that prints atsr.py

        result = {
            "name": self.name,
            "serialNumber": self.serialNumber,
            "groupNumber": self.groupNumber,
            "groupSerialNumber": self.groupSerialNumber,
            "runOrder": self.runOrder,
            "status": self.status,
            "batch": self.batch,
            "expectedResult": self.expectedResult,
            "message": self.message,
            "startDateTime": self.startDateTime,
            "endDateTime": self.endDateTime,
            "options": self.options,
            "directory": self.directory,
            "notes": self.notes,
            "output": out,
            "independent": self.independent,
            "block": self.block,
            "timelimit": self.timelimit,
            "commandList": self.commandList,
            "commandLine": self.commandLine,
            "elapsedTime": self.elapsedTime(),
            "executable": str(self.executable),
            "priority": self.priority,
            "totalPriority": self.totalPriority,
            "depends_on_serial": ds,
            "dependents_serial": [d.serialNumber for d in self.dependents],
            "waitUntil_serial": [t.serialNumber for t in self.waitUntil]
        }
        return result

    def __str__ (self):
        return str(self.status) + ' ' + self.name + ' ' + self.message

    def __repr__(self):
        return "Test #%d %s %s" %(self.serialNumber, self.name, self.status)

    def __bool__ (self):
        "It is not proper to test the truth of a test."
        self.set(FAILED, 'if test(...) not allowed.')
        log(self, echo=True)
        return False

    def setStartDateTime(self):
        "Sets date and time in the form of yyyy-mm-dd hh:mm:ss for database"
        self.startDateTime = curDateTime()
        self.startTime = time.time()

    def setEndDateTime(self):
        "Sets date and time in the form of yyyy-mm-dd hh:mm:ss for database"
        self.endDateTime = curDateTime()
        self.endTime = time.time()

    def elapsedTime(self):
        "Returns formatted elapsed time of the run."
        try:
            e = self.endTime
            s = self.startTime
            elapsed = e-s
        except AttributeError as foo:
            elapsed = 0.0

        if elapsed < 60.0:
            fmtStr = '%.2f sec' % elapsed
        else:
            fmtStr = hms(elapsed)

        return fmtStr

    def set (self, status, message):
        "Set a new status."
        self.status = status
        self.message = str(message)
        if status in (CREATED, RUNNING, INVALID, BATCHED):
            return
        if status is PASSED:
            if PASSED is self.expectedResult:
                return
            else:
                self.notes.append("Test unexpectedly PASSED, setting to FAIL")
                self.status = FAILED
                return
# Didn't pass, skip the dependents. (One could argue about this.)
        for d in self.dependents:
            if d.status is CREATED:
                d.set(SKIPPED, "Ancestor test %s %s" % (self.name, status))
# Didn't pass, but is that ok?
        if status is self.expectedResult:
            self.notes.append("Expected status achieved, %s" % status)
            self.status = EXPECTED

    def stick (cls, **options):
        """Add keyword/value pairs for subsequent tests in this file.
        """
        cls.stuck.update(options)
    stick = classmethod(stick)

    def waitNewSource(cls):
        cls.waitUntilAccumulatorStack.append(cls.waitUntilAccumulator[:])
    waitNewSource = classmethod(waitNewSource)

    def waitEndSource(cls):
        s = cls.waitUntilAccumulatorStack.pop()
        cls.waitUntilAccumulator = s[:]
        cls.waitUntil = s[:]
    waitEndSource = classmethod(waitEndSource)

    def wait(cls):
        "Create a wait boundary"
        cls.waitUntil = cls.waitUntilAccumulator[:]
    wait = classmethod(wait)

    def newGroup(cls, independent=False, **kw):
        "Sets counters so next test(s) in same AtsTestGroup"
        cls.endGroup()
        cls.groupCounter += 1
        cls.group = AtsTestGroup(cls.groupCounter)
        cls.grouped = kw
        cls.grouped['independent'] = independent
    newGroup = classmethod(newGroup)

    def endGroup(cls):
        "End this group"
        cls.group = None
        cls.grouped = {}
    endGroup = classmethod(endGroup)

    def unstick (cls, *kw):
        "Remove the named sticky options. With no arg, remove all."
        if kw:
            for k in kw:
                if k in cls.stuck:
                    del cls.stuck[k]
        else:
            cls.stuck.clear()
    unstick = classmethod(unstick)

    def tack (cls, **options):
        """Add keyword/value pairs for subsequent tests in descendent files.
           A current tacked value overrules glue
        """
        cls.tacked.update(options)
    tack = classmethod(tack)

    def untack (cls, *kw):
        "Remove the named tacked options"
        if kw:
            for k in kw:
                if k in cls.tacked:
                    del cls.tacked[k]
        else:
            cls.tacked.clear()
    untack = classmethod(untack)

    def glue (cls, **options):
        """Add keyword/value pairs for subsequent tests in ANY file.
           A current sticky value overrules glue
        """
        cls.glued.update(options)
    glue = classmethod(glue)

    def unglue (cls, *kw):
        "Remove the named glued options"
        if kw:
            for k in kw:
                if k in cls.glued:
                    del cls.glued[k]
        else:
            cls.glued.clear()
    unglue = classmethod(unglue)

    def checkGlue (cls, *kw):
        """Returns the value of the named glue options.
           If the named options does not exists, None is returned.
        """
        if kw:
            for k in kw:
                if k in cls.glued:
                    return cls.glued[k]
                else:
                    return None
    checkGlue = classmethod(checkGlue)


    def getOptions (cls):
        """Returns the dictionary of effective value of the test options
           outside of any test. Useful for debugging option problems.
           Class method.
        """
        opt = configuration.options
        options = {
            "np": 0,
            "batch": 0,
            "level": 1,
            "keep": opt.keep,
            "hideOutput": int(opt.hideOutput),
            "testStdout": opt.testStdout,
            "globalPrerunScript": opt.globalPrerunScript,
            "globalPostrunScript": opt.globalPostrunScript,
            "script": '',
            "clas": '',
            "executable": '',
        }
        options.update(AtsTest.glued)
        options.update(AtsTest.tacked)
        options.update(AtsTest.stuck)
        return options

    getOptions = classmethod(getOptions)

    def restart (self):
        AtsTest.stuck = {}
        AtsTest.glued = {}
        AtsTest.tacked = {}
        AtsTest.grouped = {}
        AtsTest.groupCounter = 0
        AtsTest.groupNumber = 0
        AtsTest.serialNumber = 0
        AtsTest.waitUntil = []
        AtsTest.waitUntilAccumulator = []
        AtsTest.waitUntilAccumulatorStack = []
    restart = classmethod(restart)


    def recordOutput (self, groupFailure):
        """Standard recorder for test. Some tests have a very large amount of output,
           so this does direct output rather than keep it in the test object.
           groupFailure is used if one member of a group died.
        """
        failures = [FAILED, TIMEDOUT, HALTED]
        # What we're going to do with the output file:
        checkit = self.options.get('check', False)
        keep = self.options.get('keep')
        magic = self.options.get('magic', '#ATS:')

        if checkit:
            self.notes.append('Please check the results of this test manually.')
            log('Please check the results of this test manually.', echo=True)

        if configuration.options.skip:
            return


        if self.testStdout != 'terminal':
            try:
                f = open(self.outname, 'r', errors='ignore')
            except IOError as e:
                self.notes = ['Missing output file.']
                log('Missing output file', self.outname, e)
                return

            if magic is not None:# Check for output that starts with magic phrase
                n = 0
                M=len(magic)
                for line in f:
                    n += 1
                    if line.startswith(magic):
                        self.output.append(line[M:-1])
            f.close()

        failed = self.status in failures
        lookatit = checkit or failed
        keepit = (keep>0) or lookatit or groupFailure
        hideIt = self.options.get('hideOutput')
        if keepit and (self.testStdout != 'terminal'):
            log.indent()
            if magic is not None:
                log('%d lines of output in %s' % (n, self.shortoutname),
                    echo=lookatit)
            else:
                log('Output in %s' % self.shortoutname,
                        echo=lookatit)
            log.dedent()

        else:
            self.fileOutDelete()

        if not hideIt and self.output:
            log("Captured output:", echo=False, logging=True)
            log.indent()
            for line in self.output:
                log(line, echo=False, logging=True)
            log.dedent()


    # =============================================================
    def stdOutLocGet(self):
        return self.testStdout

    def fileHandleGet(self):
        if self.outhandle is None:
            self.outhandle = open(self.outname, 'w')

        if self.combineOutput:
            self.errhandle = self.outhandle
        else:
            if self.errhandle is None:
                self.errhandle = open(self.errname, 'w')

        return self.outhandle, self.errhandle


    def fileHandleClose(self):
        if self.outhandle is not None:
            self.outhandle.close()
            self.outhandle = None

            if not self.combineOutput:
                if self.errhandle is not None:
                    self.errhandle.close()
            self.errhandle = None

    def fileOutNamesSet(self):
        logdir = log.directory
        fileName = ("%04d" % self.serialNumber) + "." + self.namebase +'.log'
        prerunScript = ("%04d" % self.serialNumber) + "." + self.namebase +'_global_prerun.log'
        postrunScript = ("%04d" % self.serialNumber) + "." + self.namebase +'_global_postrun.log'

        self.outname=os.path.join(logdir, fileName)
        self.globalPrerunScript_outname=os.path.join(logdir, prerunScript)
        self.globalPostrunScript_outname=os.path.join(logdir, postrunScript)
        self.shortoutname = fileName

        if self.combineOutput:
            self.errname=self.outname
        else:
            self.errname=self.outname+'.err'

    def fileOutDelete(self):
        if os.path.exists(self.outname):
            try:
                os.unlink(self.outname)
            except:
                time.sleep(1)
                try:
                    os.unlink(self.outname)
                except:
                    log('Not able to delete %s' % self.outname, echo=True, logging=True)

        if not self.combineOutput:
            if os.path.exists(self.errname):
                try:
                    os.unlink(self.errname)
                except:
                    time.sleep(1)
                    try:
                        os.unlink(self.errname)
                    except:
                        log('Not able to delete %s' % self.errname, echo=True, logging=True)
        pass
