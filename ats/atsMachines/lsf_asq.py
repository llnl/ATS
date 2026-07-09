#ATS:blueos_3_ppc64le_ib_p9 SELF lsfMachine  40
#ATS:blueos_3_ppc64le_ib    SELF lsfMachine  20
#ATS:lsf_asq                SELF lsfMachine  40

from ats import machines, debug, atsut
from ats import log, terminal
from ats import configuration
from ats.atsut import RUNNING, TIMEDOUT, PASSED, FAILED, CREATED, SKIPPED, HALTED, EXPECTED, LSFERROR, statuses

from ats.atsMachines import utils
import math
import sys, os, time
from subprocess import check_output

#
# Update python module path so we can import the 'times' module
# that is part of the ATS source code
#
tempstr = sys.executable
tempstr = tempstr.replace('bin/python','')
atsdir  = os.path.join(tempstr, 'lib/python2.7/site-packages/ats')
hwname = os.uname()[1]
#print "DEBUG 1000 atsdir=%s" % atsdir
#print "DEBUG 2000 hwname=%s" % hwname
sys.path.append ( atsdir )

if "ansel" in hwname or "sierra" in hwname or "lassen" in hwname:
    cores_per_node = 40      # there are 44 really, but some are reserved for OS
    physical_cores_per_node = 40
    cores_per_socket = 20    # there are 22 really.
else:
    cores_per_node = 20
    physical_cores_per_node = 20
    cores_per_socket = 10

from ats.times import hm, Duration, timeSpecToSec

MY_SYS_TYPE = os.environ.get('SYS_TYPE', sys.platform)

class lsfMachine (machines.Machine):
    """
    Run under LSF using bsub interactively.
    """

    remainingCapacity_numNodesReported = -1
    remainingCapacity_numProcsReported = -1
    remainingCapacity_numTestsReported = -1
    canRunNow_numProcsAvailableReported = -1
    canRunNow_saved_string = ""
    debugClass = False
    debugJsrun = False

    def init (self):

        self.runningWithinBsub = True

        # Detect how many cores have been reserved for the OS, default it to 2 if not detectable
        if "LLNL_CORE_ISOLATION" in os.environ.keys():
            self.LLNL_CORE_ISOLATION=int(os.getenv("LLNL_CORE_ISOLATION"))
        else:
            self.LLNL_CORE_ISOLATION=2

        if "LSB_MAX_NUM_PROCESSORS" in os.environ.keys():
            self.LSB_MAX_NUM_PROCESSORS=int(os.getenv("LSB_MAX_NUM_PROCESSORS"))
            self.LSB_MCPU_HOSTS=os.getenv("LSB_MCPU_HOSTS")
            self.numNodes           = int(self.LSB_MAX_NUM_PROCESSORS / physical_cores_per_node)
            self.numberMaxProcessors= self.numNodes * physical_cores_per_node
            self.npMax              = physical_cores_per_node

        else:
            if "ansel" in hwname or "sierra" in hwname or "lassen" in hwname:
                self.numNodes=4
            else:
                self.numNodes=2

            self.runningWithinBsub = False
            self.numberMaxProcessors= self.numNodes * physical_cores_per_node
            self.npMax              = self.numberMaxProcessors

        #print "DEBUG lsfMachine init self.numNodes = %d" % self.numNodes
        #print "DEBUG lsfMachine init self.npMax = %d" % self.npMax
        #print "DEBUG lsfMachine init self.numberMaxProcessors = %d" % self.numberMaxProcessors
        #print "DEBUG lsfMachine init self.runningWithinBsub is %r" % self.runningWithinBsub

        self.nodesInUse = [0] * self.numNodes

        super(lsfMachine, self).init()

    def checkForAtsProc(self):
        rshCommand= 'ps uwww'
        returnCode, runOutput= utils.runThisCommand(rshCommand)
        theLines= runOutput.split('\n')
        foundAts= False
        for aline in theLines:
            #if 'srun' in aline and 'defunct' in aline:
            if 'salloc ' in aline:
                # NO ats running.
                return 0
            if 'bin/ats ' in aline:
                foundAts= True

        if foundAts:
            # Found ats running.
            return 1
        # NO ats running.
        return 0

    def getNumberOfProcessors(self):
        # Maximum number of processors available. Number of nodes times
        # number of procs per node.
        return self.numberMaxProcessors

    def examineOptions(self, options):
        "Examine options from command line, possibly override command line choices."
        # Grab option values.
        super(lsfMachine, self).examineOptions(options)

        self.sequential = options.sequential

        #self.npMax = self.npMaxH
        if options.npMax > 0:
            self.npMax = options.npMax

        if self.runningWithinBsub:
            options.numNodes = self.numNodes

        if not self.runningWithinBsub:
            if options.numNodes > 0:
                self.numNodes = options.numNodes

        # Maximum number of processors available
        self.numberMaxProcessors = self.npMax * self.numNodes

        # Number of processors currently available
        self.numProcsAvailable = self.numberMaxProcessors

        # Maximum number of tests allowed to run at the same time.
        # This needs to be set for the manager for filter the jobs correctly.
        self.numberTestsRunningMax = self.numberMaxProcessors

        super(lsfMachine, self).examineOptions(options)

        # self.partition = options.partition

        self.numProcsAvailable     = self.numberMaxProcessors
        self.numberTestsRunningMax = self.numberMaxProcessors

        self.mpibind_executable = options.mpibind_executable
        self.old_defaults     = options.blueos_old_defaults
        self.lrun_jsrun_args  = options.blueos_lrun_jsrun_args
        self.mpibind          = options.blueos_mpibind
        self.exclusive        = options.jsrun_exclusive
        self.jsrun_exclusive  = options.jsrun_exclusive
        self.lrun             = options.blueos_lrun
        self.lrun_pack        = options.blueos_lrun_pack
        self.jsrun            = options.blueos_jsrun
        self.jsrun_omp        = options.blueos_jsrun_omp
        self.jsrun_bind       = options.blueos_jsrun_bind
        self.ompProcBind      = options.ompProcBind
        self.ngpu             = options.blueos_ngpu
        self.blueos_np        = options.blueos_np
        self.blueos_np_max    = options.blueos_np_max
        self.cpusPerTask      = options.cpusPerTask
        self.timelimit        = options.timelimit
        self.mpi_um           = options.mpi_um
        self.smpi_off         = options.smpi_off
        self.smpi_show        = options.smpi_show

        #if self.lrun_pack and self.lrun_pack == False:
        #    print("DBG 101 self.lrun_pack = False")
        #if self.lrun_pack and self.lrun_pack == True:
        #    print("DBG 102 self.lrun_pack = True")
            

        # If user specified a path to mpibind, then
        # set mpibind to True as well.
        if self.mpibind_executable != "unset":
            self.mpibind = True

        if lsfMachine.debugJsrun:
            JSRUN_DEBUG = "JSRUN 000 DEBUG lsf_asq"
            print("%s self.lrun_jsrun_args =  '%s'" % (JSRUN_DEBUG, self.lrun_jsrun_args))
            print("%s self.jsrun           =  '%s'" % (JSRUN_DEBUG, self.jsrun))
            print("%s self.jsrun_omp       =  '%s'" % (JSRUN_DEBUG, self.jsrun_omp))
            print("%s self.jsrun_bind      =  '%s'" % (JSRUN_DEBUG, self.jsrun_bind))
            # print "JSRUN 000 DEBUG lsf_asq self.jsrun_nn        =  '%s'" % self.jsrun_nn
            print("%s self.jsrun_exclusive =   %r " % (JSRUN_DEBUG, self.jsrun_exclusive))

        if lsfMachine.debugClass:
            DEBUG_LSF = "DEBUG lsfMachine Class "
            print("%s options.cuttime             = %s " % (DEBUG_LSF, options.cuttime))
            print("%s options.timelimit           = %s " % (DEBUG_LSF, options.timelimit))
            print("%s options.globalPostrunScript = %s " % (DEBUG_LSF, options.globalPostrunScript))
            print("%s options.globalPrerunScript  = %s " % (DEBUG_LSF, options.globalPrerunScript))
            print("%s options.testStdout          = %s " % (DEBUG_LSF, options.testStdout))
            print("%s options.logdir              = %s " % (DEBUG_LSF, options.logdir))
            print("%s options.level               = %s " % (DEBUG_LSF, options.level))
            print("%s options.npMax               = %s " % (DEBUG_LSF, options.npMax))
            print("%s options.reportFreq          = %s " % (DEBUG_LSF, options.reportFreq))
            print("%s options.ompNumThreads       = %s " % (DEBUG_LSF, options.ompNumThreads))
            print("%s options.sleepBeforeSrun     = %s " % (DEBUG_LSF, options.sleepBeforeSrun))
            print("%s options.continueFreq        = %s " % (DEBUG_LSF, options.continueFreq))
            print("%s options.atsrFreq            = %s " % (DEBUG_LSF, options.atsrFreq))
            print("%s options.verbose             = %s " % (DEBUG_LSF, options.verbose))
            print("%s options.debug               = %s " % (DEBUG_LSF, options.debug))
            print("%s options.info                = %s " % (DEBUG_LSF, options.info))
            print("%s options.hideOutput          = %s " % (DEBUG_LSF, options.hideOutput))
            print("%s options.keep                = %s " % (DEBUG_LSF, options.keep))
            print("%s options.logUsage            = %s " % (DEBUG_LSF, options.logUsage))
            print("%s options.okInvalid           = %s " % (DEBUG_LSF, options.okInvalid))
            print("%s options.oneFailure          = %s " % (DEBUG_LSF, options.oneFailure))
            print("%s options.sequential          = %s " % (DEBUG_LSF, options.sequential))
            print("%s options.nosrun              = %s " % (DEBUG_LSF, options.nosrun))
            print("%s options.checkForAtsProc     = %s " % (DEBUG_LSF, options.checkForAtsProc))
            print("%s options.showGroupStartOnly  = %s " % (DEBUG_LSF, options.showGroupStartOnly))
            print("%s options.removeStartNote     = %s " % (DEBUG_LSF, options.removeStartNote))
            print("%s options.removeEndNote       = %s " % (DEBUG_LSF, options.removeEndNote))
            print("%s options.skip                = %s " % (DEBUG_LSF, options.skip))
            print("%s options.blueos_exclusive    = %s " % (DEBUG_LSF, options.blueos_exclusive))
            print("%s options.mpibind             = %s " % (DEBUG_LSF, options.mpibind))
            print("%s options.mpibind_executable  = %s " % (DEBUG_LSF, options.mpibind_executable))
            print("%s options.combineOutErr       = %s " % (DEBUG_LSF, options.combineOutErr))
            print("%s options.allInteractive      = %s " % (DEBUG_LSF, options.allInteractive))
            print("%s options.filter              = %s " % (DEBUG_LSF, options.filter))
            print("%s options.glue                = %s " % (DEBUG_LSF, options.glue))

        if lsfMachine.debugClass:
            DEBUG_LSF = "DEBUG lsfMachine leaving "
            print("%s self.npMax = %d " % (DEBUG_LSF, self.npMax))
            print("%s self.npMaxH = %d " % (DEBUG_LSF, self.npMaxH))
            print("%s self.numberMaxProcessors = %d " % (DEBUG_LSF, self.numberMaxProcessors))
            print("%s self.numberTestsRunningMax = %d " % (DEBUG_LSF, self.numberTestsRunningMax))
            print("%s self.numNodes = %d " % (DEBUG_LSF, self.numNodes))
            print("%s self.numProcsAvailable = %d " % (DEBUG_LSF, self.numProcsAvailable))
            print("%s self.numberTestsRunningMax = %d " % (DEBUG_LSF, self.numberTestsRunningMax))
            print("%s self.exclusive = %r " % (DEBUG_LSF, self.exclusive))
            print("%s self.timelimit = %s " % (DEBUG_LSF, self.timelimit))

    def addOptions(self, parser):

        "Add options needed on this machine."
        parser.add_option("--numNodes", action="store", type="int", dest='numNodes',
            default = 1,
            help="Number of nodes to use")
        pass

    def getResults(self):
        """I'm not sure what this function is supposed to do"""
        return machines.Machine.getResults(self)

    def label(self):
        return "lsfMachine: %d nodes, %d processors per node, %d max procs per node, %d total procs." % (
            self.numNodes, physical_cores_per_node, self.npMax, self.numberMaxProcessors)

    def set_nt_cpus_per_task_num_nodes(self,test):
        # Command line ompNumThreads will over-ride what is in the deck.
        # Allows user to set nt on the ATS command line. If not specified.
        # will look in the deck.  If not there, will be set to 1

        if lsfMachine.debugJsrun:
            print("JSRUN 005 DEBUG")
            print("JSRUN 005 DEBUG lsf_asq test.np                 =  %d " % test.np)
            print("JSRUN 005 DEBUG self.npMax                      =  %d " % self.npMax)

        if configuration.options.ompNumThreads and configuration.options.ompNumThreads > 0:
            test.nt = configuration.options.ompNumThreads
            test.cpus_per_task = test.nt    # for compatability with another python file used by slurm and blueos machine
        else:
            test.nt = test.options.get('nt', 1)
            test.cpus_per_task = test.nt    # for compatability with another python file used by slurm and blueos machine

        if lsfMachine.debugJsrun:
            print("JSRUN 006 DEBUG lsf_asq test.nt                 =  %d " % test.nt)
            print("JSRUN 006 DEBUG lsf_asq test.cpus_per_task      =  %d " % test.cpus_per_task)

        #if (self.jsrun_nn < 1):
        #    test.num_nodes = test.options.get('nn', 0)
        #else:
        #    test.num_nodes = self.jsrun_nn

        test.num_nodes = test.options.get('nn', 0)

        if lsfMachine.debugJsrun:
            print("JSRUN 007 DEBUG test.num_nodes                  =  %s " % test.num_nodes)

        # If num_nodes not specified check to see if we are running more than 40 MPI processes, if so we need
        # multiple nodes (hosts)
        if ((test.np * test.nt) > self.npMax):
            if test.num_nodes < 1:
                if self.lrun_pack and self.lrun_pack == True:
                    if lsfMachine.debugClass:
                        print("ATS test %s detected lrun_pack option.  Will not implicitly set nn (num_nodes). Will rely on lrun to do the right thing" % (test.name))
                else:
                    test.num_nodes = math.ceil( (float(test.np) * float(test.nt)) / float(self.npMax))
                    test.nn = test.num_nodes
                    if configuration.options.verbose:
                        print("ATS setting test.nn to %i for test %s based on test.np = %i and test.nt=%i (%i x %i = %i) which spans 2 or more nodes." %
                          (test.num_nodes, test.name, test.np, test.nt, test.np, test.nt, test.np * test.nt))

        if lsfMachine.debugJsrun:
            print("JSRUN 010 DEBUG lsf_asq test.num_nodes          =  %d " % test.num_nodes)

    def calculateCommandList(self, test):

        # print "DEBUG calculateCommandList entered"

        # Number of processors needed by one job.
        import os
        timeNow            = time.strftime('%H%M%S',time.localtime())
        np  = max(test.np, 1)
        commandList = self.calculateBasicCommandList(test)
        test.jobname         = "t%d_%d%s%s" % (np, test.serialNumber, test.namebase[0:50], timeNow)
        test.blueos_np       = self.blueos_np
        test.blueos_np_max   = self.blueos_np_max
        test.cpusPerTask     = self.cpusPerTask
        test.jsrun_omp       = self.jsrun_omp
        test.jsrun_bind      = self.jsrun_bind
        test.lrun            = self.lrun
        test.lrun_pack       = self.lrun_pack
        test.lrun_jsrun_args = self.lrun_jsrun_args
        test.ompProcBind     = self.ompProcBind
        test.mpi_um          = self.mpi_um
        test.smpi_off        = self.smpi_off
        test.smpi_show       = self.smpi_show

        if lsfMachine.debugJsrun:
            print("JSRUN 020 DEBUG lsf_asq test.jsrun_omp          =  %s " % test.jsrun_omp)
            print("JSRUN 020 DEBUG lsf_asq test.jsrun_bind         =  %s " % test.jsrun_bind)
            print("JSRUN 020 DEBUG lsf_asq test.lrun_jsrun_args    =  %s " % test.lrun_jsrun_args)

        # Command line --blueos_np option will over-ride the test specific np option
        if test.blueos_np > 0:
            test.np = test.blueos_np
            np = test.blueos_np

        # Command line --blueos_np_max option will over-ride the test specific np option if
        # the test specific option is greater than the command line option
        if test.blueos_np_max > 0 and  test.np > test.blueos_np_max:
            print("Deprecation Warning: lrun_np_max and jsrun_np_max are deprecated and will be removed in the future. Use test_np_max instead.")
            test.np = test.blueos_np_max
            np = test.blueos_np_max

        lsfMachine.set_nt_cpus_per_task_num_nodes(self, test)
        num_nodes = test.num_nodes

        if lsfMachine.debugJsrun:
            print("JSRUN 022 DEBUG lsf_asq test.num_nodes          =  %d " % test.num_nodes)
            print("JSRUN 022 DEBUG lsf_asq num_nodes               =  %d " % num_nodes)

        temp_time_limit = test.options.get('timelimit', 59)
        time_limit      = Duration(temp_time_limit)
        time_secs       = timeSpecToSec(time_limit)
        time_mins       = time_secs / 60

        # Allow user to set ngpu in input deck or on ATS command line with blueos_ngpu argument
        # The input deck setting has priority.  Fall back to ATS command line option.
        test.ngpu  = test.options.get('ngpu', -1)

        # Option to run with --smpiargs=-gpu.  Useful if cudaMallocManaged memory is used
        # within MPI operations.
        if test.smpi_off == True:
            str_smpi = "--smpiargs=off"
        elif test.smpi_show == True:
            str_smpi = "--smpiargs=-show"
        elif test.mpi_um == True:
            str_smpi = "--smpiargs=\"-gpu\""
        else:
            str_smpi = " "


        str_lrun_jsrun_args = "unset"

        if test.lrun_jsrun_args != "unset":
            str_lrun_jsrun_args = test.lrun_jsrun_args
        else:
            if self.lrun == True:
                str_lrun_jsrun_args = "-v"

        str_mpibind = "/usr/tce/bin/mpibind"
        if self.mpibind_executable != "unset":
            str_mpibind = self.mpibind_executable

        #if test.mpi_um == True:
        #    str_smpi = "--smpiargs=\"-gpu\""

        if configuration.options.blueos_ngpu and configuration.options.blueos_ngpu >= 0:
            test.ngpu = configuration.options.blueos_ngpu
        else:
            if (test.ngpu < 0):
                test.ngpu = 0

        if self.ompProcBind == "unset":
            self.ompProcBind = "False"

        str_omp_display_env="OMP_DISPLAY_ENV=%s" % configuration.options.ompDisplayEnv
        str_omp_num_threads="OMP_NUM_THREADS=%d" % test.cpus_per_task
        str_omp_proc_bind="OMP_PROC_BIND=%s" %  self.ompProcBind

        if "ansel" in hwname or "sierra" in hwname or "lassen" in hwname or "manta" in hwname:

            if self.runningWithinBsub == True:

                # launch args suggested by Chris Scroeder, where the test case has the args as a test argument
                if test.options.get('lsfrun'):
                    str_args = test.options.get('lsfrun')
                    return str_args.split() + commandList
                # End of Coding suggested by Chris Scroeder

                if self.lrun == True:

                    # SAD Note 2020-02-27 test.cpus_per_task is set based on the nt or the ompNumThreads option.
                    #                     which is the number of threads to spawn.  There is a separate
                    #                     cpusPerTask which may be set as well, for allocating more cores, but
                    #                     not necessarily threading over them. Comes in handy in edge cases.
                    if test.cpus_per_task > 1:
                        str_lrun_jsrun_args="-c " + str(test.cpus_per_task) + " " + str_lrun_jsrun_args
                    elif test.cpusPerTask > 0:
                        str_lrun_jsrun_args="-c " + str(test.cpusPerTask) + " " + str_lrun_jsrun_args

                    if test.ngpu > 0:
                        str_lrun_jsrun_args="-g " + str(test.ngpu) + " " + str_lrun_jsrun_args

                    if test.lrun_pack:
                        # Add --pack as it was requested
                        str_lrun_jsrun_args="--pack " + str_lrun_jsrun_args

                    if self.mpibind_executable == "unset":
                        if self.mpibind == True:
                            str_mpibind = "--mpibind=on"
                            # If no defaults, but if user said --mpibind, then add this as it was requested
                            if self.old_defaults == False:
                                str_lrun_jsrun_args = str_lrun_jsrun_args + " --mpibind=on"
                        else:
                            str_mpibind = "--mpibind=off"
                    else:
                        # if mpibind executable specified, use it even for with no defaults
                        # Take care to add the mpibind executable as the very last argument
                        str_lrun_jsrun_args = str_lrun_jsrun_args + " " + self.mpibind_executable

                    if self.old_defaults:
                        if ( test.num_nodes > 0) :
                            return ["lrun",
                                    str_smpi,
                                    "--env", str_omp_display_env,
                                    "--env", str_omp_num_threads,
                                    "--env", str_omp_proc_bind,
                                    "-N", str(int(test.num_nodes)),
                                    "-n", str(np)
                                    ] + str_lrun_jsrun_args.split() + [ str_mpibind ] + commandList
                        else :
                            return ["lrun",
                                    str_smpi,
                                    "--env", str_omp_display_env,
                                    "--env", str_omp_num_threads,
                                    "--env", str_omp_proc_bind,
                                    "-n", str(np)
                                    ] + str_lrun_jsrun_args.split() + [ str_mpibind ] + commandList
                    else:
                        if ( test.num_nodes > 0) :
                            return ["lrun",
                                    str_smpi,
                                    "-v",
                                    "-N", str(int(test.num_nodes)),
                                    "-n", str(np)
                                    ] + str_lrun_jsrun_args.split() + commandList
                        else :
                            return ["lrun",
                                    str_smpi,
                                    "-v",
                                    "-n", str(np)
                                    ] + str_lrun_jsrun_args.split() + commandList


                # 2019-04-25 Use this for both jsrun_omp and for --jsrun_exclusive.
                #            Comment out the jsrun_omp only code below, as it works sometimes and hangs RM sometimes.
                #            Also use exclusive if user has specified the num_nodes, or if it was set due to
                #            the number of processors x threads requested for the test.
                elif self.jsrun_exclusive == True or self.jsrun_omp == True or test.num_nodes > 0:

                    # if omp or nn > 0, set exclusive for later use as well
                    self.jsrun_exclusive = True

                    #
                    # If user did not specify number of nodes, calculated based on the number of processors requested.
                    #
                    if test.num_nodes < 1:
                        test.num_nodes = math.ceil(float(test.np) / float(self.npMax))
                        if configuration.options.verbose:
                            print("ATS setting numNodes for test %i to %i based on test.np = %i,  number of cores per node of %i, and --exclusive option" %
                                  (test.serialNumber, test.num_nodes, test.np, self.npMax))

                    if lsfMachine.debugJsrun:
                        print("JSRUN 090 DEBUG test.num_nodes =  %d " % test.num_nodes)
                    #
                    # Now that we know how many nodes we need, loop over the array of nodesInUse
                    #   and find the indexe for nodes not in use (slot will be 0 in this case)
                    #   If found, save the host/node number into the test.rs_nodesToUse
                    #   and set the self.nodesInUse[slotNum] to 1 to indicate it is now being used.
                    #
                    test.rs_nodesToUse = []
                    numNodesFound = 0
                    slotNum = -1
                    for slot in self.nodesInUse:
                        slotNum += 1
                        if numNodesFound < test.num_nodes:
                            if slot == 0:
                                # The rs file that jsrun uses starts numbering hosts at 1, not 0, so +1
                                test.rs_nodesToUse.append(slotNum + 1)
                                numNodesFound += 1
                                self.nodesInUse[slotNum]  = 1

                    # create the file with the nodes to use
                    test.rs_filename = os.getcwd() + "/%i_ats_test_%04d_rs" % (os.getpid(), test.serialNumber)

                    # print "SAD DEBUG self.LLNL_CORE_ISOLATION = %d\n" % self.LLNL_CORE_ISOLATION

                    file = open(test.rs_filename,"w")
                    rs_cntr = -1
                    for node in test.rs_nodesToUse:
                        rs_cntr += 1
                        # file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 , gpu: 0 1 2 3 , mem: 0-130740 1-130740 }\n" % (rs_cntr, node))
                        if self.LLNL_CORE_ISOLATION == 0:
                            if "manta" in hwname:
                                file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 gpu: 0 1 2 3 }\n" % (rs_cntr, node))
                            else:
                                file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43, gpu: 0 1 2 3 }\n" % (rs_cntr, node))
                        elif self.LLNL_CORE_ISOLATION == 1:
                            if "manta" in hwname:
                                file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 gpu: 0 1 2 3 }\n" % (rs_cntr, node))
                            else:
                                file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41, gpu: 0 1 2 3 }\n" % (rs_cntr, node))
                        else:
                            if "manta" in hwname:
                                file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 gpu: 0 1 2 3 }\n" % (rs_cntr, node))
                            else:
                                file.write("RS %i: { host: %i, cpu: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39, gpu: 0 1 2 3 }\n" % (rs_cntr, node))
                    file.close()

                    #if lsfMachine.debugJsrun:
                    if configuration.options.verbose:
                        print("ATS created LSF jsrun resource file for test %s = %s" % (test.name, test.rs_filename))
                        with open(test.rs_filename, 'r') as fin:
                            print(fin.read())

                    if str_lrun_jsrun_args == "unset":
                        str_lrun_jsrun_args = ""

                    if lsfMachine.debugJsrun:
                        JSRUN_DEBUG = "JSRUN 220 DEBUG lsf_asq"
                        print("%s test.jsrun_bind =  '%s'" % (JSRUN_DEBUG, test.jsrun_bind))
                        print("%s self.mpibind =  '%s'" % (JSRUN_DEBUG, self.mpibind))
                        print("%s str_mpibind =  '%s'" % (JSRUN_DEBUG, str_mpibind))

                    if test.jsrun_bind == "unset":
                        if self.mpibind:
                            str_lrun_jsrun_args = str_lrun_jsrun_args + " -b none " + str_mpibind
                        else:
                            if self.old_defaults:
                                str_lrun_jsrun_args = str_lrun_jsrun_args + " -b rs "
                            else:
                                str_lrun_jsrun_args = str_lrun_jsrun_args + " -b rs "
                    else:
                        if self.mpibind:
                            str_lrun_jsrun_args = str_lrun_jsrun_args + " -b " + test.jsrun_bind + " " + str_mpibind
                        else:
                            str_lrun_jsrun_args = str_lrun_jsrun_args + " -b " + test.jsrun_bind

                    if self.old_defaults:
                        return ["jsrun",
                            str_smpi,
                            "--env", str_omp_display_env,
                            "--env", str_omp_num_threads,
                            "--env", str_omp_proc_bind,
                            "-U",   test.rs_filename,
                            "--np", str(np),
                        ] + str_lrun_jsrun_args.split() + commandList
                    else:
                        return ["jsrun",
                            str_smpi,
                            "-U",   test.rs_filename,
                            "--np", str(np),
                        ] + str_lrun_jsrun_args.split() + commandList


                # This is also the default whether or not --jsrun was specified.
                # I wanted the --jsrun option in case we flip the default.
                # 2019-05-06:  Useful for non threaded MPI Code with or without GPU support.
                else:
                    if lsfMachine.debugJsrun:
                        print("JSRUN 100 DEBUG lsf_asq ")

                    test.jsrun_bind_r = "rs"
                    test.jsrun_bind_none = "none"

                    if test.jsrun_bind != "unset":
                        test.jsrun_bind_r    = test.jsrun_bind
                        test.jsrun_bind_none = test.jsrun_bind

                    # if mpibind specified, use it even for with no defaults
                    if self.mpibind == True:
                        if str_lrun_jsrun_args == "unset":
                            str_lrun_jsrun_args = str_mpibind
                        else:
                            str_lrun_jsrun_args = str_lrun_jsrun_args + " " + str_mpibind

                    cpu_per_rs = np * test.cpus_per_task

                    if str_lrun_jsrun_args == "unset":
                        str_lrun_jsrun_args = ""

                    if lsfMachine.debugJsrun:
                        print("JSRUN 110 DEBUG lsf_asq test.jsrun_bind_r =  %s " % test.jsrun_bind_r)
                        print("JSRUN 110 DEBUG lsf_asq test.jsrun_bind_none =  %s " % test.jsrun_bind_none)
                        print("JSRUN 110 DEBUG lsf_asq test.jsrun_bind =  %s " % test.jsrun_bind)
                        print("JSRUN 110 DEBUG lsf_asq self.mpibind =  %s " % self.mpibind)
                        print("JSRUN 110 DEBUG lsf_asq str_lrun_jsrun_args =  %s " % str_lrun_jsrun_args)
                        print("JSRUN 110 DEBUG lsf_asq cpu_per_rs =  %d " % cpu_per_rs)


                    if self.old_defaults:

                        return ["jsrun",
                            str_smpi,
                            "--env", str_omp_display_env,
                            "--env", str_omp_num_threads,
                            # "--env", str_omp_proc_bind, SAD questions if this is useful, comment out
                            "-n", "1",
                            "-r", "1",
                            "-a", str(np),
                            "-c", str(cpu_per_rs),
                            "-g", str(test.ngpu),
                            "-b", test.jsrun_bind
                        ] + str_lrun_jsrun_args.split() + commandList
                    else:
                        if test.cpus_per_task > 1:
                            return ["jsrun",
                                str_smpi,
                                "--np", str(np),
                                "-c", str(test.cpus_per_task),
                                "-g", str(test.ngpu),
                                "-b", test.jsrun_bind_r
                            ] + str_lrun_jsrun_args.split() + commandList

                        elif test.cpusPerTask > 0:
                            return ["jsrun",
                                str_smpi,
                                "--np", str(np),
                                "-c", str(test.cpusPerTask),
                                "-g", str(test.ngpu),
                                "-b", test.jsrun_bind_r
                            ] + str_lrun_jsrun_args.split() + commandList

                        else:
                            # 2020-02-28 SAD testing this for all runs
                            #return ["jsrun",
                            #    "--np", str(np),
                            #    "-g", str(test.ngpu),
                            #    "-b", test.jsrun_bind_r
                            #] + str_lrun_jsrun_args.split() + commandList

                            return ["jsrun",
                                str_smpi,
                                "-n", "1",
                                "-r", "1",
                                "-a", str(np),
                                "-c", str(cpu_per_rs),
                                "-g", str(test.ngpu)
                            ] + str_lrun_jsrun_args.split() + commandList

            # This following section is for Ansel, running from the login node.  So bsub is needed.
            #
            else:

                print("ATS DISABLED ON LOGIN NODE OF ANSEL.  PLEASE RUN IN AN ALLOCATION.")
                sys.exit(-1)
        #
        # This is not sierra, lassen, ansel, or manta, what is this?
        #
        else:
            print("ATS ERROR: Do not know what LSF machine %s is " % hwname)
            sys.exit(-1)

    def canRun(self, test):
        """Is this machine able to run the test interactively when resources become available?
           If so return ''.  Otherwise return the reason it cannot be run here.
        """
        np = max(test.np, 1)
        if np > self.numberMaxProcessors:
            return "Too many processors needed : %d requested %d is the max" % (np, self.numberMaxProcessors)

        return ''

    def canRunNow(self, test):
        "Is this machine able to run this test now? Return True/False"

        # Get the number of processors needed and the number of nodes needed for this test
        # if specified.  Get the number of nodes remaining for exclusive use.
        #
        numberNodesRemaining = self.numNodes - self.numberNodesExclusivelyUsed
        np = max(test.np, 1)

        lsfMachine.set_nt_cpus_per_task_num_nodes(self, test)

        #test.num_nodes = test.options.get('nn', 0)
        #nt = test.options.get('nt', -1)
        #if (nt < 1):
        #    if configuration.options.ompNumThreads and configuration.options.ompNumThreads > 0:
        #        nt = configuration.options.ompNumThreads
        #    else:
        #        nt = 1

        canRunNow_debug = lsfMachine.debugClass
        canRunNow_debug = False

        if self.jsrun_exclusive:
            if test.num_nodes < 1:
                test.num_nodes = math.ceil(float(test.np) / float(self.npMax))

        #print "DEBG test.num_nodes = %i\n" % test.num_nodes

        nosrun  = test.options.get('nosrun', False)

        # If the LSF system thinks the user already had 3 or more running jobs,
        # then we can not run yet, as LSF will simply submit cancel the
        # pending job
        if self.runningWithinBsub == False:
            my_output = check_output("lsfjobs | grep `whoami` | wc -l",
                                     shell=True, text=True)
            my_num_lsf_jobs_running = int(my_output)

            if nosrun == False:
                string = "%d" % my_num_lsf_jobs_running
                if my_num_lsf_jobs_running > self.numNodes - 1:
                    if string != lsfMachine.canRunNow_saved_string:
                        print("ATS LSF Development: User has %d jobs already running.  Waiting for one to finish" % my_num_lsf_jobs_running)
                    lsfMachine.canRunNow_saved_string = string
                    return False

        if configuration.options.sequential:
            if (self.numProcsAvailable < self.numberMaxProcessors):
                if configuration.options.verbose:
                    string = "%d_%d" % (self.numProcsAvailable, self.numberMaxProcessors)
                    if string != lsfMachine.canRunNow_saved_string:
                        lsfMachine.canRunNow_saved_string = string
                        if canRunNow_debug:
                            print("DEBUG canRunNow returning FALSE based on sequential option: ")

                return False

        # if the test object has a specified number of nodes defined, then see if we have enuf nodes available
        # In this case, since num_nodes has been specified, set np to be the number of nodes
        #   requested x the max number of processors per node
        if test.num_nodes > 0:

            np = test.num_nodes * self.npMax

            my_numProcsAvailable = self.numProcsAvailable

            if canRunNow_debug:
                string = "%i >= %i and %i >= %i" % (numberNodesRemaining, test.num_nodes, my_numProcsAvailable, np)
                if string != lsfMachine.canRunNow_saved_string:
                    lsfMachine.canRunNow_saved_string = string
                    if numberNodesRemaining >= test.num_nodes and my_numProcsAvailable >= np:
                        print("DEBUG canRunNow returning TRUE  based on node avail: %d is  >= %d and proc avail : %d is  >= %d (%s)" %
                              (test.num_nodes, numberNodesRemaining, my_numProcsAvailable, np,test.name))
                    else:
                        print("DEBUG canRunNow returning FALSE based on node avail: %d not >= %d  or proc avail : %d not >= %d (%s)" %
                              (test.num_nodes, numberNodesRemaining, my_numProcsAvailable, np,test.name))

            # print "DEBUG canRunNow returning %d >= %d and %d >= %d" % (numberNodesRemaining, test.num_nodes, my_numProcsAvailable, np)
            return numberNodesRemaining >= test.num_nodes and my_numProcsAvailable >= np

        # else, back to our original programming, see if there are enuf procs available
        else:
            if canRunNow_debug:
                string = "%i >= (%i * %i)" % (self.numProcsAvailable, np, nt)
                if string != lsfMachine.canRunNow_saved_string:
                    lsfMachine.canRunNow_saved_string = string
                    if self.numProcsAvailable >= (test.np * test.nt):
                        print("DEBUG canRunNow returning TRUE  based on proc avail: %d is  >= %d (%s)" %
                              (self.numProcsAvailable, (np * nt),test.name))
                    else:
                        print("DEBUG canRunNow returning FALSE based on proc avail: %d not >= %d (%s)" %
                              (self.numProcsAvailable, (np * nt),test.name))

            #print "DEBUG canRunNow returning self.numProcsAvailable %d >= np %d?" % (self.numProcsAvailable, np)
            return self.numProcsAvailable >= (test.np * test.nt)

    def noteLaunch(self, test):
        """A test has been launched."""
        my_np = max(test.np, 1)
        my_nn = 0
        my_nt = 1

        if hasattr(test, 'num_nodes'):
            my_nn = max(test.num_nodes, 0)

        if hasattr(test, 'nt'):
            my_nt = max(test.nt, 1)

        test.num_procs_used = my_np * my_nt
        if hasattr(test, 'rs_nodesToUse') and len(test.rs_nodesToUse) > 0 and test.num_nodes > 0:
            test.num_procs_used = test.num_nodes * physical_cores_per_node

        #print "DEBUG noteLaunch 100 test.name = %s test.num_nodes = %i nn = %i np = %i nt = %i num_procs_used = %i" % (test.name, test.num_nodes, my_nn, my_np, my_nt, test.num_procs_used)
        #print "DEBUG noteLaunch 100 decreasing self.numProcsAvailable from %d to %d" % (self.numProcsAvailable, self.numProcsAvailable - test.num_procs_used)
        #print self.nodesInUse

        self.numProcsAvailable          -= test.num_procs_used

        if hasattr(test, 'rs_nodesToUse'):
            #print "DEBUG noteLaunch 100 len test.rs_nodesToUse = %i" % len(test.rs_nodesToUse)
            if len(test.rs_nodesToUse) > 0:
                #print "DEBUG noteLaunch 100 increasing self.numberNodesExclusivelyUsed from %d to %d out of %d" % (self.numberNodesExclusivelyUsed, self.numberNodesExclusivelyUsed + test.num_nodes, self.numNodes)
                self.numberNodesExclusivelyUsed += test.num_nodes
        #else:
        #    print "DEBUG noteLaunch 100 empty test.rs_nodesToUse"

        if self.jsrun_exclusive == True:
            numSlotsUsed = 0
            for slot in self.nodesInUse:
                if slot == 1:
                    numSlotsUsed += 1
            if self.numberNodesExclusivelyUsed != numSlotsUsed:
                print("ATS Error: numSlotsUsed = %i numberNodesExclusivelyUsed = %i\n" %
                      (numSlotsUsed, self.numberNodesExclusivelyUsed))
                sys.exit(-1)

    def noteEnd(self, test):
        """A test has finished running. """
        my_np = max(test.np, 1)
        if hasattr(test, 'nt'):
            my_nt = max(test.nt, 1)
        else:
            my_nt = 1

        if hasattr(test, 'ngpu'):
            my_ngpu = max(test.ngpu, 0)
        else:
            my_ngpu = 0

        msgHosts=""
        if hasattr(test, 'rs_nodesToUse'):
            if len(test.rs_nodesToUse) > 0:
                msgHosts = "Hosts = [ "
                for host in test.rs_nodesToUse:
                    msgHosts += str(host) + " "
                msgHosts += "]"

        msg = '%s #%4d %s, %s nn=%d, np=%d, nt=%d, ngpu=%d %s' % \
            ("Stop ", test.serialNumber, test.name, msgHosts, test.num_nodes, my_np, my_nt, my_ngpu, time.asctime())

        if "ENVIRONMENT" in os.environ.keys():
            my_environment = os.environ.get("ENVIRONMENT", 'novalue')

        if my_environment == "INTERACTIVE":
            os.system("stty sane")  # Keep the interactive terminal sane on blueos

        if my_environment == "INTERACTIVE":
            os.system("stty sane")  # Keep the interactive terminal sane on blueos

        self.numProcsAvailable          += test.num_procs_used

        if hasattr(test, 'rs_nodesToUse'):
            cntNumNodes = 0
            for nodeNum in test.rs_nodesToUse:
                cntNumNodes += 1
                slotNum = nodeNum - 1   # nodeNum is 1 based, convert to 0 based index forarray
                if slotNum > self.numNodes:
                    print("ATS Error: noteEnd, slotNum=%i self.npMax=%i\n" %
                          (slotNum, self.numNodes))
                    sys.exit(-1)
                self.nodesInUse[slotNum] = 0

            if cntNumNodes != test.num_nodes:
                print("ATS Error: noteEnd, cntNumNodes=%i test.num_nodes=%i\n" %
                      (cntNumNodes, test.num_nodes))
                sys.exit(-1)

            #print "DEBUG noteEnd 100 decreasing self.numberNodesExclusivelyUsed from %d to %d out of %d" % (self.numberNodesExclusivelyUsed, self.numberNodesExclusivelyUsed - test.num_nodes, self.numNodes)
            self.numberNodesExclusivelyUsed -= test.num_nodes

        if hasattr(test, 'rs_filename'):
            if os.path.isfile(test.rs_filename):
                #print "DEBUG noteEnd unlinking '%s'" % test.rs_filename
                os.unlink(test.rs_filename)
            else:
                print("ATS Error: Can not find file '%s'\n" % test.rs_filename)

        #print self.nodesInUse
        return msg

    def periodicReport(self):
        "Report on current status of tasks"
        return

    def remainingCapacity(self):
        """How many nodes or processors are free? ?"""
        numberNodesRemaining = self.numNodes              - self.numberNodesExclusivelyUsed
        numberTestsRemaining = self.numberTestsRunningMax - self.numberTestsRunning
        if self.jsrun_exclusive == True:
            if numberNodesRemaining != lsfMachine.remainingCapacity_numNodesReported:
                lsfMachine.remainingCapacity_numNodesReported = numberNodesRemaining
                if  lsfMachine.debugClass:
                    print("DEBUG remainingCapacity AAA %d Nodes Available" % numberNodesRemaining)

            if numberNodesRemaining < 1:
                if False:
                    print("DEBUG remainingCapacity AAA1 returning 0 ")
                return 0
            else:
                if False:
                    print("DEBUG remainingCapacity AAA2 returning %d " % (numberNodesRemaining))
                return numberNodesRemaining
        else:
            if numberNodesRemaining < 1:
                if numberNodesRemaining != lsfMachine.remainingCapacity_numNodesReported:
                    lsfMachine.remainingCapacity_numNodesReported = numberNodesRemaining
                    if False:
                        print("DEBUG remainingCapacity BBB %d Nodes Available" % numberNodesRemaining)

                if numberNodesRemaining < 1:
                    if False:
                        print("DEBUG remainingCapacity BBB1 returning 0 ")
                    return 0
                else:
                    if False:
                        print("DEBUG remainingCapacity BBB2 returning %d " % (numberNodesRemaining))
                    return numberNodesRemaining
            else:
                if self.numProcsAvailable != lsfMachine.remainingCapacity_numProcsReported:
                    lsfMachine.remainingCapacity_numProcsReported = self.numProcsAvailable
                    if False:
                        print("DEBUG remainingCapacity CCC self.numProcsAvailable = %d " % (self.numProcsAvailable))

                if self.numProcsAvailable < 1:
                    if False:
                        print("DEBUG remainingCapacity DDD returning 0 ")
                    return 0
                else:
                    if False:
                        print("DEBUG remainingCapacity EEE returning %d " % (self.numProcsAvailable))
                    return self.numProcsAvailable

    def kill(self, test):
        "Final cleanup if any."
        # kill the test
        import subprocess
        if self.runningWithinBsub == False:
            if test.status is RUNNING or test.status is TIMEDOUT:
                try:
                    print("ATS cancelling job: bkill -J " + test.jobname)
                    retcode= subprocess.call("bkill -J " + test.jobname, shell=True)
                    if retcode < 0:
                        log("---- bkill() in lsf_asq.py, command= bkill -J %s failed with return code -%d  ----" %  (test.jobname, retcode), echo=True)
                except OSError as e:
                    log("---- bkill() in lsf_asq.py, execution of command failed (bkill -J %s) failed:  %s----" %  (test.jobname, e), echo=True)
