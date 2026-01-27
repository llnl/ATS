#ATS:SlurmProcessorScheduled SELF SlurmProcessorScheduled 12
#ATS:slurm8                  SELF SlurmProcessorScheduled  8
#ATS:slurm12                 SELF SlurmProcessorScheduled 12
#ATS:slurm16                 SELF SlurmProcessorScheduled 16
#ATS:slurm20                 SELF SlurmProcessorScheduled 20
#ATS:slurm24                 SELF SlurmProcessorScheduled 24
#ATS:slurm32                 SELF SlurmProcessorScheduled 32
#ATS:slurm36                 SELF SlurmProcessorScheduled 36
#ATS:slurm48                 SELF SlurmProcessorScheduled 48
#ATS:slurm56                 SELF SlurmProcessorScheduled 56
#ATS:slurm112                 SELF SlurmProcessorScheduled 112
#ATS:slurm128                 SELF SlurmProcessorScheduled 128
#ATS:toss_3_x86_64_ib        SELF SlurmProcessorScheduled 36
#ATS:toss_3_x86_64           SELF SlurmProcessorScheduled 36
#ATS:toss_4_x86_64_ib        SELF SlurmProcessorScheduled 36
#ATS:toss_4_x86_64           SELF SlurmProcessorScheduled 36
#ATS:toss_4_x86_64_ib_cray   SELF SlurmProcessorScheduled 64

import inspect
import math
import re, sys, os, time, subprocess

from ats import machines, debug, atsut
from ats import log, terminal
from ats import configuration
from ats.atsut import RUNNING, TIMEDOUT, PASSED, FAILED, CREATED, SKIPPED, HALTED, EXPECTED, statuses
from ats.atsMachines import utils
from ats.atsMachines import lcMachines

MY_SYS_TYPE = os.environ.get('SYS_TYPE', sys.platform)

class SlurmProcessorScheduled(lcMachines.LCMachineCore):

    # Strings used to determine which node a user wants the test to run
    # Used with same_node var
    _cached_nodes = None  # static/class variable
    node_list = [] 

    lastMessageLine = 0
    remainingCapacity_numNodesReported = -1
    remainingCapacity_numProcsReported = -1
    remainingCapacity_numTestsReported = -1
    canRunNow_numProcsAvailableReported = -1
    canRunNow_saved_string = ""
    checkForAtsProcNumRemovedProcs = 0
    debugClass = False
    canRunNow_debugClass = False
    slurm_version_str=""
    slurm_version_int=0

    def init(self):

        # Identify the slurm version so ATS may account for differences
        # in slurm behavior
        tstr = subprocess.check_output(['srun', '--version'], text=True)
        tarray=tstr.split() 
        SlurmProcessorScheduled.slurm_version_str=tarray[1]
        log('SLURM VERSION STRING', SlurmProcessorScheduled.slurm_version_str)
        tarray=re.split('[\.\-]',SlurmProcessorScheduled.slurm_version_str)
        SlurmProcessorScheduled.slurm_version_int=(int(tarray[0]) * 1000) + (int(tarray[1]) * 100) + (int(tarray[2]))
        log('SLURM VERSION NUMBER', SlurmProcessorScheduled.slurm_version_int)

        self.runningWithinSalloc = True

        if "SLURM_JOB_NUM_NODES" in os.environ.keys():
            self.numNodes= int(os.getenv("SLURM_JOB_NUM_NODES"))
            self.npMax= int(os.getenv("SLURM_JOB_CPUS_PER_NODE", "1").split("(")[0])
        elif "SLURM_NNODES" in os.environ.keys():
            self.numNodes= int(os.getenv("SLURM_NNODES"))
            self.npMax= int(os.getenv("SLURM_JOB_CPUS_PER_NODE", "1").split("(")[0])
        else:
            self.runningWithinSalloc = False
            self.npMax= self.numberTestsRunningMax

        # log('SAD DEBUG SlurmProcessorScheduled init self.numNodes = ', self.numNodes)
        # log('SAD DEBUG SlurmProcessorScheduled init self.npMax = ', self.npMax)

        super(SlurmProcessorScheduled, self).init()

        # Call get_physical_node to cache the hardware node listing before starting jobs.
        # This is required for the same_node functionality.
        try:
            self.get_physical_node(0)
        except RuntimeError:
            # If you are not in an allocation, an exception will be thrown.
            # We ignore the exception here and allow _cached_nodes to be None.
            # If you are not using same_node, this is fine.  If you are using same_node,
            # it should throw an exception when setting up the command list.
            pass

    def expand_nodelist(self, nodelist_field):
        """
        Expand a Flux nodelist string like 'rzadams[1002,1005-1007]' into a list of node names.
        Handles multiple comma-separated patterns.
        """
        nodes = []
        # Regex to find patterns like prefix[range] or prefixNNNN
        pattern = re.compile(r'([a-zA-Z0-9_-]+)(?:\[(.*?)\])?')
        for match in pattern.finditer(nodelist_field):
            prefix = match.group(1)
            bracket = match.group(2)
            if bracket:
                for part in bracket.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        nodes.extend([f"{prefix}{i}" for i in range(start, end + 1)])
                    else:
                        nodes.append(f"{prefix}{part}")
            else:
                nodes.append(prefix)
        return nodes

    def get_physical_node(self, rel_index):
        """
        Given a relative node number, return the actual physical node within
        the Slurm allocation.
        """
        if self._cached_nodes is None:
            nodelist_str = os.environ.get("SLURM_JOB_NODELIST")
            if not nodelist_str:
                raise RuntimeError(
                    "SLURM_JOB_NODELIST is not set. Are you running inside a Slurm allocation/job?"
                )

            # Option 1: if your expand_nodelist already handles Slurm-style nodelists,
            # just call it directly:
            self._cached_nodes = self.expand_nodelist(nodelist_str)

            # Option 2 (alternative): use scontrol show hostnames to expand for you:
            # out = subprocess.check_output(
            #     f"scontrol show hostnames {nodelist_str}", shell=True
            # ).decode().splitlines()
            # self._cached_nodes = out

            # Optional logging
            log(("Info: Physical Hardware Nodes: %s" % self._cached_nodes), echo=True)
            # log(f"Info: Physical Hardware Nodes: {self._cached_nodes}", echo=True)

        nodes = self._cached_nodes
        if rel_index < 0 or rel_index >= len(nodes):
            raise IndexError(f"Relative index {rel_index} out of range (0-{len(nodes)-1})")
        return nodes[rel_index]


    # will be taking up one of the cores.
    #
    # Let's try and do this with ENV VARS instead
    #
    def checkForAtsProc(self):
        if self.checkForAtsProcFlag == True:
            if "SLURM_PTY_PORT" in os.environ.keys() or "SLURM_STEP_ID" in os.environ.keys():
                if SlurmProcessorScheduled.debugClass:
                    print("DEBUG checkForAtsProc returning 1 (TRUE)")
                return 1
            else:
                if SlurmProcessorScheduled.debugClass:
                    print("DEBUG checkForAtsProc returning 0 (FALSE)")
                return 0
        else:
            if SlurmProcessorScheduled.debugClass:
                print("DEBUG (checkForAtsProc is False) checkForAtsProc returning 0 (FALSE)")
            return 0


    def getNumberOfProcessors(self):
        return self.numberMaxProcessors

    def examineOptions(self, options):
        "Examine options from command line, possibly override command line choices."
        # Grab option values.
        # Note, this machines.Machine.examineOptions call will reset self.numberTestsRunningMax
        # self.numberTestsRunningMax is set in init(), not need to call machines.Machine.examineOptions
        # machines.Machine.examineOptions(self, options)

        self.distribution        = options.distribution
        self.checkForAtsProcFlag = options.checkForAtsProc

        # Does slurm see the ATS process itself as utilizing a core?
        self.slurmSeesATSProcessAsUsingACore = False
        if "SLURM_PTY_PORT" in os.environ.keys() or "SLURM_STEP_ID" in os.environ.keys():
            self.slurmSeesATSProcessAsUsingACore = True
            if not configuration.options.quiet:
                print("""
ATS NOTICE: Slurm sees ATS or Shell as itself using a CPU.
            ATS Will ignore 'nn' (number of nodes) test options and allow processes
            to span multiple nodes for better throughput and to help prevent srun hangs.

            NOTE: This feature may not fix possible hangs resulting from a single test
                  case which utilizes all allocated cores. Slurm may not see all 
                  the cores as usable and accept the job but not schedule it, resulting in a hang

            The node spanning behavior may be overridden with the --strict_nn ATS option.

            CAUTION: Use of --strict_nn may result in slurm/srun hangs which are 
                     beyond the control of ATS, depending on how the nodes were allocated
""")


        if SlurmProcessorScheduled.debugClass:
            DEBUG_SLURM = "DEBUG SlurmProcessorScheduled Class"
            print("%s options.cuttime             = %s " % (DEBUG_SLURM, options.cuttime))
            print("%s options.distribution        = %s " % (DEBUG_SLURM, options.distribution))
            print("%s options.timelimit           = %s " % (DEBUG_SLURM, options.timelimit))
            print("%s options.globalPostrunScript = %s " % (DEBUG_SLURM, options.globalPostrunScript))
            print("%s options.globalPrerunScript  = %s " % (DEBUG_SLURM, options.globalPrerunScript))
            print("%s options.testStdout          = %s " % (DEBUG_SLURM, options.testStdout))
            print("%s options.logdir              = %s " % (DEBUG_SLURM, options.logdir))
            print("%s options.level               = %s " % (DEBUG_SLURM, options.level))
            print("%s options.npMax               = %s " % (DEBUG_SLURM, options.npMax))
            print("%s options.reportFreq          = %s " % (DEBUG_SLURM, options.reportFreq))
            print("%s options.ompNumThreads       = %s " % (DEBUG_SLURM, options.ompNumThreads))
            print("%s options.cpusPerTask         = %s " % (DEBUG_SLURM, options.cpusPerTask))
            print("%s options.continueFreq        = %s " % (DEBUG_SLURM, options.continueFreq))
            print("%s options.quiet               = %s " % (DEBUG_SLURM, options.quiet))
            print("%s options.verbose             = %s " % (DEBUG_SLURM, options.verbose))
            print("%s options.debug               = %s " % (DEBUG_SLURM, options.debug))
            print("%s options.info                = %s " % (DEBUG_SLURM, options.info))
            print("%s options.hideOutput          = %s " % (DEBUG_SLURM, options.hideOutput))
            print("%s options.keep                = %s " % (DEBUG_SLURM, options.keep))
            print("%s options.logUsage            = %s " % (DEBUG_SLURM, options.logUsage))
            print("%s options.okInvalid           = %s " % (DEBUG_SLURM, options.okInvalid))
            print("%s options.oneFailure          = %s " % (DEBUG_SLURM, options.oneFailure))
            print("%s options.sequential          = %s " % (DEBUG_SLURM, options.sequential))
            print("%s options.nosrun              = %s " % (DEBUG_SLURM, options.nosrun))
            print("%s options.salloc              = %s " % (DEBUG_SLURM, options.salloc))
            print("%s options.sargs               = %s " % (DEBUG_SLURM, options.sargs))
            print("%s options.checkForAtsProc     = %s " % (DEBUG_SLURM, options.checkForAtsProc))
            print("%s options.showGroupStartOnly  = %s " % (DEBUG_SLURM, options.showGroupStartOnly))
            print("%s options.removeStartNote     = %s " % (DEBUG_SLURM, options.removeStartNote))
            print("%s options.removeEndNote       = %s " % (DEBUG_SLURM, options.removeEndNote))
            print("%s options.skip                = %s " % (DEBUG_SLURM, options.skip))
            print("%s options.exclusive           = %s " % (DEBUG_SLURM, options.exclusive))
            print("%s options.mpibind             = %s " % (DEBUG_SLURM, options.mpibind))
            print("%s options.combineOutErr       = %s " % (DEBUG_SLURM, options.combineOutErr))
            print("%s options.allInteractive      = %s " % (DEBUG_SLURM, options.allInteractive))
            print("%s options.filter              = %s " % (DEBUG_SLURM, options.filter))
            print("%s options.glue                = %s " % (DEBUG_SLURM, options.glue))

        if options.npMax > 0:
            self.npMax = options.npMax
        else:
            if self.runningWithinSalloc:
                self.npMax = max(self.npMaxH, self.npMax)
            else:
                self.npMax = self.npMaxH

        if self.runningWithinSalloc:
            options.numNodes = self.numNodes

        if not self.runningWithinSalloc:
            super(SlurmProcessorScheduled, self).examineOptions(options)
            self.numNodes  = options.numNodes
            self.partition = options.partition

        self.numberMaxProcessors   = self.npMax * self.numNodes

        # If the user did not set npMax by hand
        # AND if we running within an salloc partition
        # AND if one cpu is being used already for our shell or whatever
        # Then subtract one core from the max number of processors (across all nodes)
        if options.npMax <= 0:
            if self.runningWithinSalloc==True:
                if self.checkForAtsProc():
                    self.numberMaxProcessors -= 1
                    SlurmProcessorScheduled.checkForAtsProcNumRemovedProcs = 1

        self.numProcsAvailable     = self.numberMaxProcessors
        self.numberTestsRunningMax = self.numberMaxProcessors

        self.exclusive = options.exclusive
        self.mpibind   = options.mpibind
        self.salloc    = options.salloc
        self.sargs     = options.sargs
        self.toss_nn   = options.toss_nn
        self.strict_nn = options.strict_nn
        self.useMinNodes = options.useMinNodes
        self.timelimit = options.timelimit

        if SlurmProcessorScheduled.debugClass:
            DEBUG_OPTIONS = "DEBUG examineOptions leaving"
            print("%s self.npMax = %d " % (DEBUG_OPTIONS, self.npMax))
            print("%s self.npMaxH = %d " % (DEBUG_OPTIONS, self.npMaxH))
            print("%s self.numberMaxProcessors = %d " % (DEBUG_OPTIONS, self.numberMaxProcessors))
            print("%s self.numberTestsRunningMax = %d " % (DEBUG_OPTIONS, self.numberTestsRunningMax))

    def addOptions(self, parser):
        """Add options needed on this machine."""

        temp_uname = os.uname()
        host = temp_uname[1]

        add_partition = 'pdebug'
        if host.startswith('rzwhamo'):
            add_partition = 'nvidia'

        parser.add_option("--partition", action="store", type="string", dest='partition',
            default = add_partition,
            help = "Partition in which to run jobs with np > 0")

        parser.add_option("--sargs", action="store", type="string", dest='sargs',
            default = "",
            help = "extra srun/salloc args")

        parser.add_option("--numNodes", action="store", type="int", dest='numNodes',
           default = 2,
           help="Number of nodes to use")

        parser.add_option("--distribution", action="store", type="string", dest='distribution',
           default = 'unset',
           help="srun distribution of mpi processes across nodes")


    def getResults(self):
        """I'm not sure what this function is supposed to do"""
        return machines.Machine.getResults(self)

    def label(self):
        return "SlurmProcessorScheduled: %d nodes, %d processors per node." % (
            self.numNodes, self.npMax)

    def set_nt_num_nodes(self,test):

        # Command line option nt over-rides what is in the deck.
        test.nt = 1
        if configuration.options.ompNumThreads > 0:
            test.nt = configuration.options.ompNumThreads
        else:
            if 'nt' in test.options:
                test.nt = test.options.get('nt', 1)

        test.cpus_per_task = -1
        if configuration.options.cpusPerTask > -1:
            test.cpus_per_task = configuration.options.cpusPerTask
        else:
            if 'cpus_per_task' in test.options:
                test.cpus_per_task = test.options.get('cpus_per_task', 1)

        # Command line option toss_nn over-rides what is in the deck.
        if (self.toss_nn < 0):
            test.num_nodes = test.options.get('nn', 0)
        else:
            test.num_nodes = self.toss_nn

        # If num_nodes not specified check to see if we are running more than 40 MPI processes, if so we need
        # multiple nodes (hosts)
        if ((test.np * test.nt) > self.npMax):
            if test.num_nodes < 1:
                if (self.toss_nn < 0):
                    test.num_nodes = math.ceil( (float(test.np) * float(test.nt)) / float(self.npMax))
                    test.nn = test.num_nodes
                    if configuration.options.verbose:
                        print("ATS setting test.nn to %i for test %s based on test.np = %i and test.nt=%i (%i x %i = %i) which spans 2 or more nodes." %
                              (test.num_nodes, test.name, test.np, test.nt, test.np, test.nt, test.np * test.nt))

    def calculateCommandList(self, test):
        """Prepare for run of executable using a suitable command. First we get the plain command
         line that would be executed on a vanilla machine, then we modify it if necessary
         for use on this machines.
        """

        import os

        np                 = max(test.np, 1)
        distribution       = self.distribution        # default is cyclic, by can be overridden with --distribution=xxx
        test.runningWithinSalloc = self.runningWithinSalloc
        commandList        = self.calculateBasicCommandList(test)
        timeNow            = time.strftime('%H%M%S', time.localtime())
        test.jobname       = "t%d_%d%s%s" % (np, test.serialNumber, test.namebase[0:50], timeNow)
        test_time          = test.options.get('time', 0)

        SlurmProcessorScheduled.set_nt_num_nodes(self, test)
        num_nodes   = test.num_nodes
        num_threads = test.nt
        # minNodes    = np / self.npMax + (np % self.npMax != 0 )
        minNodes    = math.ceil((float(np) * float(num_threads)) / float(self.npMax))

        #print("DEBUG SAD JULY np=%i num_threads=%i" % (np, num_threads))
        #print("DEBUG SAD JULY test.num_nodes=%i num_nodes=%i" % (test.num_nodes, num_nodes))

        #
        # --exclusive is the default, but it can be switched via the --share ats argument
        #
        srun_ex_or_sh = '--comment="noexclusive"'
        if self.exclusive == True:
            srun_ex_or_sh = "--exclusive"

        # If the user requests that a test be run on the same node then we store the identifying string
        # and then spread the node identifiers across the nodes we have access to. This way users dont need
        # to think about how many nodes there are or which one they want to run on.
        srun_nodelist = '--comment="no_nodelist"'
        same_node = test.options.get('same_node', None)
        if same_node is not None:
            if same_node not in self.node_list:
                self.node_list.append(same_node)
            rel_node = self.node_list.index(same_node) % self.numNodes
            physical_node = self.get_physical_node(rel_node)
            srun_nodelist = '--nodelist=%s' % physical_node
            distribution="no_distribution"

        # print("SAD DEBUG NODELIST = %s" % (srun_nodelist))

        # 2021-07-14 SAD Old logic where we were using overlap for newer SchedMD slurm update
        #                May not be needed now, but leave this in for a bit in case
        #                we need to revert
        #   if SlurmProcessorScheduled.slurm_version_int >= 21100:
        #        srun_ex_or_sh = "--overlap"
        #    else:
        #        srun_ex_or_sh = "--exclusive"

        temp_uname = os.uname()
        host = temp_uname[1]

        srun_mpi_type='--comment="nompitype"'
        if host.startswith('rznevaxxx'):
            srun_mpi_type='--mpi=pmi2'

        srun_unbuffered='--comment="nounbuffered"'
        if configuration.options.unbuffered:
            srun_unbuffered='--unbuffered'

        if MY_SYS_TYPE.startswith('toss'):
            # none means to not specify mpibind at all, use slurm defaults
            if self.mpibind == "none":
                srun_mpibind = "--comment=nompindspeccification"
            else:
                srun_mpibind = "--mpibind=%s" % self.mpibind
        else:
            srun_mpibind = "--comment=nompindspeccification"

        #
        # If the distribution is unset, then set it to cyclic
        # If same_node was processed, make a comment, do not add a distribution opion though
        #
        if distribution == 'unset':
            srun_distribution="--distribution=cyclic"
        elif distribution=='no_distribution':
            srun_distribution="--comment=no_distribution"
        else:
            srun_distribution="--distribution=%s" % distribution

        # set more srun defaults here, may be over-ridden below
        # For running within an allocation we set it to allow slurm to use all
        # the nodes as the default
        srun_nodes="--nodes=%i-%i" % (1, self.numNodes)
        srun_partition="--comment=nopartition"
        srun_cpus_per_task="--cpus-per-task=1"

        # Set the --partition option here
        # If not within an salloc, then set the partition to be used for the srun line
        if self.runningWithinSalloc == False and self.partition:
            srun_partition="--partition=%s" % self.partition

        if self.sargs:
            extra_sargs = self.sargs
        else:
            extra_sargs = "--comment=nosargs"


        # Set the --nodes srun option  here
        #
        # print("DEBUG SAD JULY num_nodes=%i minNodes=%i self.numNodes=%i " % (num_nodes, minNodes, self.numNodes))
        #
        # DEBUG SAD JULY num_nodes=0 minNodes=1 self.numNodes=3
        
        # Note these 3 node values are:
        #   num_nodes     : the nn value for the test, will be 0 if not requested by the user
        #   minNodes      : the number of nodes calculated based on the np (number of mpi) processes and threads
        #   self.numNodes : the number of nodes allocated for this run of ATS for all concurren tests, typically 3-6 nodes
         
        # we are running on the login node, each test will be a separate srun line and allocation
        if self.runningWithinSalloc == False:                           
            if num_nodes > 0:
                srun_nodes="--nodes=%i-%i" % (num_nodes, num_nodes)     # If user set nn then honor it
            else:
                if self.exclusive == True:
                    test.numNodesToUse = minNodes                       # If user asked for exclusive access to each node
                    srun_nodes="--nodes=%i-%i" % (minNodes, minNodes)   # then set nodes based on minNodes, which is
                else:                                                   # determined by the number of processors
                    nodes="--comment=nonodes"                           # This will allow tests to share nodes with other users

        # We are running on a pre-allocated set of node
        # If the num_nodes is > 0 (ie the user specified "nn=1" or something similar for the test)
        elif num_nodes > 0:
            if (self.strict_nn == False):
                srun_nodes="--nodes=%i-%i" % (num_nodes, self.numNodes)
            else:
                srun_nodes="--nodes=%i-%i" % (num_nodes, num_nodes)

        elif self.useMinNodes == True:
            srun_nodes="--nodes=%i-%i" % (minNodes, minNodes)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 
        # ----------------------------------------------------------------------------------------------------------------------------
        if num_nodes > 0:

            test.numNodesToUse = num_nodes

            if     "SLURM_JOB_CPUS_PER_NODE" in os.environ.keys():
                self.slurm_cpus_on_node = int(os.getenv("SLURM_JOB_CPUS_PER_NODE", "1").split("(")[0])
            elif   "SLURM_CPUS_ON_NODE" in os.environ.keys():
                self.slurm_cpus_on_node = int(os.getenv("SLURM_CPUS_ON_NODE"))
            elif self.npMax > 0:
                self.slurm_cpus_on_node = self.npMax
            else:
                print("ATS ERROR: 'nn' specified neither SLURM_JOB_CPUS_PER_NODE nor SLURM_CPUS_ON_NODE nor self.npMax is set.")
                sys.exit(1)

            tasks_per_node        = np / num_nodes
            tasks_per_node_modulo = np % num_nodes
            if (tasks_per_node < 1) :
                tasks_per_node = 1

            if not tasks_per_node_modulo == 0:

                #  Bump up the tasks per node by 1 as at least 1 node will have extra tasks.
                tasks_per_node +=1

                if self.salloc == False:
                    print(test)
                    print("ATS Warning: np=%i nn=%i" % (np, num_nodes))
                    print("             number_of_processes (%i) is not evenly divisible by number_of_nodes (%i)"  % (np, num_nodes))
                    print("             %i modulo %i = %i " % (np, num_nodes, tasks_per_node_modulo))
                    print(" ")
                    print("             %s " % test.name)
                    print(" ")

            if test.cpus_per_task > -1:

                cpus_per_task = int(test.cpus_per_task)

            else:
                if (num_threads > 1):

                    cpus_per_task = int(num_threads)

                    # If ATS is running in such a way that slurm sees all the cores AND
                    # nn is > 1 and nt > 1 then the user wants a dedicated node.
                    # In this case, bump up the cpus_per_task to achieve this under slurm.
                    # Do not let slurm pack a partial set of nodes and let other nodes sit idle.
                    if self.slurmSeesATSProcessAsUsingACore == False:
                        all_the_cpus_per_task = int(self.slurm_cpus_on_node / tasks_per_node)
                        if all_the_cpus_per_task > cpus_per_task:
                            cpus_per_task = all_the_cpus_per_task

                else:
                    cpus_per_task = int(self.slurm_cpus_on_node / tasks_per_node)

                # NOTE 123 SAD 2012-12-12
                # If the user has specified a job which will utilize all the nodes and cpus_per_task is > 1
                # we can get slurm to run the test by bumping down the cpus_per_task. Do not do this if
                # the cpus_per_task was explicitly set.  But it will allow the test to run if cpus_per_task
                # was set based on the openmp number of threads.  It may be less efficient, depending on how
                # the threads are bound to cores, but it will run.
                if self.slurmSeesATSProcessAsUsingACore:
                    while (cpus_per_task > 1) and ((np * cpus_per_task) >= self.numberMaxProcessors):
                        cpus_per_task -= 1

                test.cpus_per_task  = cpus_per_task

            test.tasks_per_node = tasks_per_node

            if test.cpus_per_task > 0:
                srun_cpus_per_task="--cpus-per-task=%i" % test.cpus_per_task
            elif test.cpus_per_task == 0:
                srun_cpus_per_task="--comment=nocpuspertask"

            if SlurmProcessorScheduled.debugClass:
                print("SAD DEBUG SRUN100")

            # launch args suggested by Chris Scroeder, where the test case has the args as a test argument
            if test.options.get('tossrun'):
                str_args = test.options.get('tossrun')
                return str_args.split() + commandList
            # End of Coding suggested by Chris Scroeder

            if self.salloc :
                return ["salloc", srun_partition, srun_ex_or_sh, srun_nodes, extra_sargs] + commandList
            else:
                return ["srun", srun_mpi_type, "--label", "-J", test.jobname,
                    srun_partition, srun_ex_or_sh, srun_unbuffered, srun_mpibind, srun_distribution, srun_nodes, srun_cpus_per_task, srun_nodelist,
                    "--ntasks=%i" % np, extra_sargs \
                   ] + commandList

        # ----------------------------------------------------------------------------------------------------------------------------
        # If we are here then num_nodes <= 0 (ie it was not specified)
        # ----------------------------------------------------------------------------------------------------------------------------
        if test.cpus_per_task > -1:
            cpus_per_task = int(test.cpus_per_task)

        else:
            # default cpus_per_task to 1 if not specified
            cpus_per_task = int(1)

            # if set to num_threads if specified (and if test.cpus_per_task is not specified)
            if (num_threads > 1):
                cpus_per_task = int(num_threads)

            # see NOTE 123 above for explanation here
            if self.slurmSeesATSProcessAsUsingACore:
                while (cpus_per_task > 1) and ((np * cpus_per_task) >= self.numberMaxProcessors):
                    cpus_per_task -= 1

            test.cpus_per_task  = cpus_per_task

        if test.cpus_per_task > 0:
            srun_cpus_per_task="--cpus-per-task=%i" % test.cpus_per_task
        elif test.cpus_per_task == 0:
            srun_cpus_per_task="--comment=nocpuspertask"

        if SlurmProcessorScheduled.debugClass:
            print("SAD DEBUG SRUN800 ")


        if self.salloc :
            return ["salloc", srun_partition, srun_ex_or_sh, srun_nodes, extra_sargs] + commandList
        else:
            return ["srun", srun_mpi_type, "--label", "-J", test.jobname,
               srun_partition, srun_ex_or_sh, srun_unbuffered, srun_mpibind, srun_distribution, srun_nodes, srun_cpus_per_task, srun_nodelist,
               "--ntasks=%i" % np, extra_sargs, \
               ] + commandList

    def canRun(self, test):
        """Is this machine able to run the test interactively when resources become available?
           If so return ''.  Otherwise return the reason it cannot be run here.
        """
        np = max(test.np, 1)
        if np > self.numberMaxProcessors:
            return "Too many processors needed (%d)" % np

        return ''

    def canRunNow(self, test):
        "Is this machine able to run this test now? Return True/False"

        #
        # Print Debug method used by just this class
        #
        def printDebug(self, numberNodesRemaining, num_nodes, np):
            #if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
            if SlurmProcessorScheduled.canRunNow_debugClass:
                print("DEBUG canRunNow ================================================================================================")
                print("DEBUG canRunNow self.numNodes                    =%d" % (self.numNodes))
                print("DEBUG canRunNow self.numberNodesExclusivelyUsed  =%d" % (self.numberNodesExclusivelyUsed))
                print("DEBUG canRunNow self.npMax                       =%d" % (self.npMax))
                print("DEBUG canRunNow numberNodesRemaining             =%d" % (numberNodesRemaining))
                print("DEBUG canRunNow num_nodes                        =%d" % (num_nodes))
                print("DEBUG canRunNow self.numProcsAvailable           =%d" % (self.numProcsAvailable))
                print("DEBUG canRunNow self.numberMaxProcessors         =%d" % (self.numberMaxProcessors))
                print("DEBUG canRunNow np                               =%d" % (np))
                print("DEBUG canRunNow self.numberTestsRunningMax       =%d" % (self.numberTestsRunningMax))
                sequential = test.options.get('sequential', False)
                print("DEBUG canRunNow sequential                       =", sequential)

        # Get the number of processors needed and the number of nodes needed for this test
        # if specified.  Get the number of nodes remaining for exclusive use.
        #
        numberNodesRemaining = self.numNodes - self.numberNodesExclusivelyUsed
        np        = max(test.np, 1)
        num_nodes = test.options.get('nn', -1)

        # how many nodes are needed?  The test case may have specified -nn, or if a user
        # is running with --exclusive, we will calculate this based on the np option.
        # and the number of processors on each node
        #
        if (num_nodes <= 0):
            if self.exclusive == True and not "SLURM_JOBID" in os.environ.keys():
                num_nodes = np / self.npMax + (np % self.npMax != 0 )

        sequential = test.options.get('sequential', False)
        if sequential == True:
            if (self.numProcsAvailable < self.numberMaxProcessors):
                if configuration.options.verbose or SlurmProcessorScheduled.canRunNow_debugClass:
                    string = "%d_%d" % (self.numProcsAvailable, self.numberMaxProcessors)
                    if string != SlurmProcessorScheduled.canRunNow_saved_string:
                        SlurmProcessorScheduled.canRunNow_saved_string = string
                        printDebug(self, numberNodesRemaining, num_nodes, np)
                        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
                            print("DEBUG canRunNow returning FALSE based on sequential option: numProcsAvailable = %d < numberMaxProcessors = %d" % (self.numProcsAvailable, self.numberMaxProcessors))

                return False

        # if the test object has nn defined, then see if we have enuf nodes available
        # In this case, since nn has been specified, set np to be the number of nodes
        #   requested x the max number of processors per node
        if num_nodes > 0:
            np = num_nodes * self.npMax
            my_numProcsAvailable = self.numProcsAvailable + SlurmProcessorScheduled.checkForAtsProcNumRemovedProcs

            if configuration.options.verbose or SlurmProcessorScheduled.canRunNow_debugClass:
                string = "%d_%d" % (numberNodesRemaining, my_numProcsAvailable)
                if string != SlurmProcessorScheduled.canRunNow_saved_string:
                    SlurmProcessorScheduled.canRunNow_saved_string = string
                    if numberNodesRemaining >= num_nodes and my_numProcsAvailable >= np:
                        printDebug(self, numberNodesRemaining, num_nodes, np)
                        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
                            print("DEBUG canRunNow returning TRUE  based on node avail: %d is  >= %d and proc avail : %d is  >= %d" % (numberNodesRemaining, num_nodes, my_numProcsAvailable, np))
                    else:
                        printDebug(self, numberNodesRemaining, num_nodes, np)
                        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
                            print("DEBUG canRunNow returning FALSE based on node avail: %d not >= %d or proc avail : %d not >= %d" % (numberNodesRemaining, num_nodes, my_numProcsAvailable, np))

            return numberNodesRemaining >= num_nodes and my_numProcsAvailable >= np

        # else, back to our original programming, see if there are enuf procs available
        else:
            if configuration.options.verbose or SlurmProcessorScheduled.canRunNow_debugClass:
                if self.numProcsAvailable != SlurmProcessorScheduled.canRunNow_numProcsAvailableReported:
                    SlurmProcessorScheduled.canRunNow_numProcsAvailableReported = self.numProcsAvailable
                    if self.numProcsAvailable >= np:
                        printDebug(self, numberNodesRemaining, num_nodes, np)
                        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
                            print("DEBUG canRunNow returning TRUE  based on proc avail: %d is  >= %d " % (self.numProcsAvailable, np))
                    else:
                        printDebug(self, numberNodesRemaining, num_nodes, np)
                        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
                            print("DEBUG canRunNow returning FALSE based on proc avail: %d not >= %d " % (self.numProcsAvailable, np))

            return self.numProcsAvailable >= np

    def noteLaunch(self, test):
        """A test has been launched."""
        np = max(test.np, 1)
        self.numProcsAvailable -= (np * test.cpus_per_task)
        test.cpus_per_task_for_noteEnd = test.cpus_per_task
        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
            print("DEBUG noteLaunch decreased self.numProcsAvailable by (%d x %d) to %d " % (np,  test.cpus_per_task, self.numProcsAvailable))

    def noteEnd(self, test):
        """A test has finished running. """

        SlurmProcessorScheduled.set_nt_num_nodes(self, test)
        my_np = max(test.np, 1)
        my_nt = max(test.nt, 1)
        my_nn = max(test.num_nodes, 0)

        self.numProcsAvailable += (my_np * test.cpus_per_task_for_noteEnd)
        if SlurmProcessorScheduled.debugClass or SlurmProcessorScheduled.canRunNow_debugClass:
            print("DEBUG noteEnd increased self.numProcsAvailable by (%d x %d) to %d " % (my_np, test.cpus_per_task_for_noteEnd, self.numProcsAvailable))

        msg = '%s #%4d %s,  nn=%d, np=%d, nt=%d, ngpu=0 %s' % \
            ("Stop ", test.serialNumber, test.name, my_nn, my_np, my_nt, time.asctime())

        return msg

    def periodicReport(self):
        "Report on current status of tasks"
        if len(self.running):
            terminal("CURRENTLY RUNNING %d tests:" % len(self.running),
                     " ".join([t.name for t in self.running]) )
        terminal("-"*80)
        terminal("CURRENTLY UTILIZING %d of %d processors." % (
            self.numberMaxProcessors - self.numProcsAvailable, self.numberMaxProcessors) )
        terminal("-"*80)

    def remainingCapacity(self):
        """How many nodes or processors are free? ?"""
        numberNodesRemaining = self.numNodes              - self.numberNodesExclusivelyUsed
        numberTestsRemaining = self.numberTestsRunningMax - self.numberTestsRunning

        #if SlurmProcessorScheduled.debugClass:
        #    print "DEBUG remainingCapacity ================================================================================================"
        #    print "DEBUG remainingCapacity self.numNodes                    =%d" % (self.numNodes)
        #    print "DEBUG remainingCapacity self.numberNodesExclusivelyUsed  =%d" % (self.numberNodesExclusivelyUsed)
        #    print "DEBUG remainingCapacity self.numProcsAvailable           =%d" % (self.numProcsAvailable)
        #    print "DEBUG remainingCapacity self.numberTestsRunningMax       =%d" % (self.numberTestsRunningMax)
        #    print "DEBUG remainingCapacity self.numberTestsRunning          =%d" % (self.numberTestsRunning)
        #    print "DEBUG remainingCapacity numberNodesRemaining             =%d" % (numberNodesRemaining)
        #    print "DEBUG remainingCapacity numberTestsRemaining             =%d" % (numberTestsRemaining)

        if self.exclusive == True and not "SLURM_JOBID" in os.environ.keys():
            if numberNodesRemaining != SlurmProcessorScheduled.remainingCapacity_numNodesReported:
                SlurmProcessorScheduled.remainingCapacity_numNodesReported = numberNodesRemaining

            if numberNodesRemaining < 1:
                if SlurmProcessorScheduled.canRunNow_debugClass:
                    if inspect.getframeinfo(inspect.currentframe()).lineno != SlurmProcessorScheduled.lastMessageLine:
                        SlurmProcessorScheduled.lastMessageLine = inspect.getframeinfo(inspect.currentframe()).lineno - 1
                        print("DEBUG remainingCapacity returning %d nodes available (A)" % 0)
                return 0
            else:
                if SlurmProcessorScheduled.canRunNow_debugClass:
                    if inspect.getframeinfo(inspect.currentframe()).lineno != SlurmProcessorScheduled.lastMessageLine:
                        SlurmProcessorScheduled.lastMessageLine = inspect.getframeinfo(inspect.currentframe()).lineno - 1
                        print("DEBUG remainingCapacity returning %d nodes available (A)" % numberNodesRemaining)
                return numberNodesRemaining
        else:
            if numberNodesRemaining < 1:
                if numberNodesRemaining != SlurmProcessorScheduled.remainingCapacity_numNodesReported:
                    SlurmProcessorScheduled.remainingCapacity_numNodesReported = numberNodesRemaining

                if numberNodesRemaining < 1:
                    if SlurmProcessorScheduled.canRunNow_debugClass:
                        if inspect.getframeinfo(inspect.currentframe()).lineno != SlurmProcessorScheduled.lastMessageLine:
                            SlurmProcessorScheduled.lastMessageLine = inspect.getframeinfo(inspect.currentframe()).lineno - 1
                            print("DEBUG remainingCapacity returning %d nodes available (B)" % 0)
                    return 0
                else:
                    if SlurmProcessorScheduled.canRunNow_debugClass:
                        if inspect.getframeinfo(inspect.currentframe()).lineno != SlurmProcessorScheduled.lastMessageLine:
                            SlurmProcessorScheduled.lastMessageLine = inspect.getframeinfo(inspect.currentframe()).lineno - 1
                            print("DEBUG remainingCapacity returning %d nodes available (B)" % numberNodesRemaining)
                    return numberNodesRemaining
            else:
                if self.numProcsAvailable != SlurmProcessorScheduled.remainingCapacity_numProcsReported:
                    SlurmProcessorScheduled.remainingCapacity_numProcsReported = self.numProcsAvailable

                if self.numProcsAvailable < 1:
                    if SlurmProcessorScheduled.canRunNow_debugClass:
                        if inspect.getframeinfo(inspect.currentframe()).lineno != SlurmProcessorScheduled.lastMessageLine:
                            SlurmProcessorScheduled.lastMessageLine = inspect.getframeinfo(inspect.currentframe()).lineno - 1
                            print("DEBUG remainingCapacity returning %d numProcsAvailable available (C)" % 0)
                    return 0
                else:
                    if SlurmProcessorScheduled.canRunNow_debugClass:
                        if inspect.getframeinfo(inspect.currentframe()).lineno != SlurmProcessorScheduled.lastMessageLine:
                            SlurmProcessorScheduled.lastMessageLine = inspect.getframeinfo(inspect.currentframe()).lineno - 1
                            print("DEBUG remainingCapacity returning %d numProcsAvailable available (C)" % self.numProcsAvailable)
                    return self.numProcsAvailable

# ################################################################################################################### #
#                                               End of File                                                           #
# ################################################################################################################### #
