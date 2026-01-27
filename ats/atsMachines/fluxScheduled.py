#ATS:flux00             SELF FluxScheduled 2

"""
This module defines the ``FluxScheduled`` class.
Allocation and flux session managed by `atsflux`. See /bin/atsflux.py for more details.

Author: William Hobbs
        <hobbs17@llnl.gov>

"""

import os
import sys
import time
import subprocess
import re
from math import ceil

from ats import terminal
from ats.atsMachines import lcMachines
from ats.tests import AtsTest
from ats.util.generic_utils import runCommand
from ats import configuration
from ats import log

class FluxScheduled(lcMachines.LCMachineCore):
    """
    A class to initialize Flux if necessary and return job statements
    from ATS tests.
    """

    _cached_nodes = None  # static/class variable
    debug = False
    debug_canRunNow = False
    debug_noteLaunch = False
    flux_outstanding_jobs = 0       # Track the number of submitted jobs yet to finish
    flux_outstanding_mpi_tasks = 0  # Track the number of outstanding submitted mpi tasks across all jobs

    def init(self):
        """
        Sets ceiling on number of nodes and cores in the allocation.
        Defines a persistent handle to use to connect to the broker.
        """
        # Add the flux python library to the system path
        flux_python_path = runCommand("flux config builtin python_path")
        sys.path.append(flux_python_path[0].strip())
        import flux
        import flux.job
        self.fluxHandle = flux.Flux()
        self.numNodes = int(
            flux.resource.list.resource_list(self.fluxHandle).get().up.nnodes
        )
        self.maxCores = int(
            flux.resource.list.resource_list(self.fluxHandle).get().up.ncores
        )
        self.numCores = int(
            flux.resource.list.resource_list(self.fluxHandle).get().up.ncores
        )
        self.numGPUs= int(
            flux.resource.list.resource_list(self.fluxHandle).get().up.ngpus
        )

        # coresPerGPU is needed to get the -c option correct
        # when running with GPUs.
        if self.numGPUs != 0:
            self.coresPerGPU = int(self.numCores / self.numGPUs)
        else:
            self.coresPerGPU = 0
        self.coresPerNode = int(self.numCores / self.numNodes)

        # Strings used to determine which node a user wants the test to run
        # Used with same_node var
        self.node_list = []

        # Maintain for backwards compatability with projects
        # Allow user to over-ride the coresPerNode
        # Other schedulers call this npMax, but for flux we are calling this coresPerNode
        # But honor the old NP_MAX env variable if it exists
        if "NP_MAX" in os.environ.keys():
            self.coresPerNode = int(os.getenv("NP_MAX"))  
            self.maxCores = self.coresPerNode * self.numNodes

        self.numProcsAvailable = self.maxCores
        self.numNodesAvailable = self.numNodes
        self.numGPUsAvailable  = self.numGPUs

        super(FluxScheduled, self).init()

        # Not used in this module, but is necessary in management.py
        self.numberTestsRunningMax = self.maxCores
        self.npMax  = self.maxCores
        self.npMaxH = self.maxCores

        if FluxScheduled.debug:
            log(("DEBUG: FluxScheduled init : self.numNodes              =%i" % (self.numNodes)), echo=True)
            log(("DEBUG: FluxScheduled init : self.maxCores              =%i" % (self.maxCores)), echo=True)
            log(("DEBUG: FluxScheduled init : self.numCores              =%i" % (self.numCores)), echo=True)
            log(("DEBUG: FluxScheduled init : self.numGPUs               =%i" % (self.numGPUs)), echo=True)
            log(("DEBUG: FluxScheduled init : self.npMax                 =%i" % (self.npMax)), echo=True)
            log(("DEBUG: FluxScheduled init : self.npMaxH                =%i" % (self.npMaxH)), echo=True)
            log(("DEBUG: FluxScheduled init : self.coresPerGPU           =%i" % (self.coresPerGPU)), echo=True)
            log(("DEBUG: FluxScheduled init : self.coresPerNode          =%i" % (self.coresPerNode)), echo=True)
            log(("DEBUG: FluxScheduled init : self.numProcsAvailable     =%i" % (self.numProcsAvailable)), echo=True)
            log(("DEBUG: FluxScheduled init : self.numNodesAvailable     =%i" % (self.numNodesAvailable)), echo=True)
            log(("DEBUG: FluxScheduled init : self.numGPUsAvailable      =%i" % (self.numGPUs)), echo=True)

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
        Given a relative node number, return the actual physical node within the flux allocation.
        Works for any node prefix (e.g., rzadams, elcap, tuo, syz).
        """
        if FluxScheduled._cached_nodes is None:
            out = subprocess.check_output("flux resource list", shell=True).decode()
            nodelist_field = None
            for line in out.splitlines():
                if line.strip().startswith("free"):
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        nodelist_field = parts[-1]
                        break
            if nodelist_field is None:
                raise RuntimeError("Could not find NODELIST field in flux resource list output.")
            FluxScheduled._cached_nodes = self.expand_nodelist(nodelist_field)
            log(("Info: Physical Hardware Nodes: %s" % FluxScheduled._cached_nodes), echo=True)

        nodes = FluxScheduled._cached_nodes
        if rel_index < 0 or rel_index >= len(nodes):
            raise IndexError(f"Relative index {rel_index} out of range (0-{len(nodes)-1})")
        return nodes[rel_index]


    def kill(self, test):
        """
        Final cleanup if any. Not implemented for Flux yet.
        """

    def examineOptions(self, options):
        """
        Optparse (soon argparse) parameters from command-line options
        for ATS users. Needed for functionality with .ats files.

        :param options: The options available to a user in test.ats files.
        """
        self.timelimit                 = options.timelimit
        self.flux_nn                   = options.flux_nn
        self.num_concurrent_jobs       = options.num_concurrent_jobs
        self.num_concurrent_mpi_tasks  = options.num_concurrent_mpi_tasks
        self.cuttime                   = options.cuttime
        self.flux_run_args             = options.flux_run_args
        self.gpus_per_task             = options.gpus_per_task
        self.test_np_max               = options.test_np_max
        self.no_time_limit             = options.no_time_limit
        self.use_flux_rm               = options.use_flux_rm
        self.cpx                       = options.cpx
        self.flux_exclusive            = options.flux_exclusive

        # Command line option --npMax will over-ride flux detection of cores per node 
        # and related vars.  Similar to setting based on NP_MAX above in the init() function, but
        # this is from the command line
        if options.npMax > 0:
            self.coresPerNode = options.npMax
            self.maxCores = self.coresPerNode * self.numNodes
            self.numProcsAvailable = self.maxCores
            self.npMax  = self.maxCores
            self.npMaxH = self.maxCores
            self.numberTestsRunningMax = self.maxCores

        # If num_concurrent_mpi_tasks was not set, it will be -1.  In this case
        # set this to be the numProcsAvailable in the allocation.
        if self.num_concurrent_mpi_tasks < 0:
            self.num_concurrent_mpi_tasks = self.numProcsAvailable

        if FluxScheduled.debug:
            log(("DEBUG: FluxScheduled examineOptions : self.timelimit=%s" % (self.timelimit)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.cuttime=%s" % (self.cuttime)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.flux_run_args=%s" % (self.flux_run_args)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.num_concurrent_jobs=%i" % (self.num_concurrent_jobs)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.num_concurrent_mpi_tasks=%i" % (self.num_concurrent_mpi_tasks)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.gpus_per_task=%s" % (self.gpus_per_task)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.test_np_max=%s" % (self.test_np_max)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.no_time_limit=%s" % (self.no_time_limit)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.use_flux_rm=%s" % (self.use_flux_rm)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.cpx=%s" % (self.cpx)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.flux_exclusive=%s" % (self.flux_exclusive)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.npMax=%i" % (self.npMax)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.npMaxH=%i" % (self.npMaxH)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.numberTestsRunningMax =%i" % (self.numberTestsRunningMax)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.numProcsAvailable =%i" % (self.numProcsAvailable)), echo=True)
            log(("DEBUG: FluxScheduled examineOptions : self.numNodesAvailable =%i" % (self.numNodesAvailable)), echo=True)

        if self.use_flux_rm:
            log("Info: Will use flux resource manager to verify free resources", echo=True)

        if self.cpx or self.within_cpx_allocation():
            log("NOTICE: Running in CPX mode", echo=True)
            os.environ['FLUX_MPIBIND_USE_TOPOFILE'] = "1"
            log("NOTICE: CPX mode Setting FLUX_MPIBIND_USE_TOPOFILE to 1", echo=True)
            os.environ['MPIBIND_TOPOFILE'] = "/collab/usr/global/tools/mpi/mpibind/topo/tuo-cpx-lgpus.xml"
            log("NOTICE: CPX mode Setting MPIBIND_TOPOFILE to /collab/usr/global/tools/mpi/mpibind/topo/tuo-cpx-lgpus.xml", echo=True)
            
    def set_nt_num_nodes(self, test):
        """
        Set the test options test.num_nodes (nn), test.nt (number of threads), and 
        test.ngpu (number of gpus), and test.cpus_per_task (number of cores per task)
        """

        # Command line option nt over-rides what is in the deck.
        test.nt = 1
        if configuration.options.ompNumThreads > 0:
            test.nt = configuration.options.ompNumThreads
        else:
            if 'nt' in test.options:
                test.nt = test.options.get('nt', 1)

        # set ngpu_per_task based on 
        test.gpus_per_task = 0                                          # Default to 0
        if self.gpus_per_task is not None:                              # Command line gpus_per_task is highest priority
            test.gpus_per_task = self.gpus_per_task
        elif 'gpus_per_task' in test.options:                           # Per test option 'gpus_per_task' is second priority
            test.gpus_per_task = test.options.get('gpus_per_task', 1)
        elif 'ngpu' in test.options:                                    # Per test option 'ngpu' is third priority
            test.gpus_per_task = test.options.get('ngpu', 1)            # and is here for backwards compatability with existing decks.

        test.ngpu = test.gpus_per_task                                  # So that the schedulers.py file will print ngpu
                                                                        # maintains backwards compatibility

        # cpus per task is related to num threads and num_gpus_per_task , but 
        # it is also meaningful for non threaded and non GPU runs
        # where we want to reserve more than 1 core per mpi rank
        # So default it to 'nt' which was set above, but
        # allow it to be set separately as well. 
        test.cpus_per_task = test.nt
        if configuration.options.cpusPerTask > -1:
            test.cpus_per_task = configuration.options.cpusPerTask
        else:
            if 'cpus_per_task' in test.options:
                test.cpus_per_task = test.options.get('cpus_per_task', 1)

        # The above set cpus_per_task based on the number of threads requested.
        # Now see if we need to increase it for the number of gpus per task as well.
        # This can only increase this setting, so we will take the max of this 
        # calculation and the cpus_per_task that was just set above.
        cpus_per_task_based_on_gpus = test.gpus_per_task * self.coresPerGPU

        if (cpus_per_task_based_on_gpus > test.cpus_per_task):
            test.cpus_per_task = cpus_per_task_based_on_gpus

        # Command line option flux_nn over-rides what is in the deck.
        if (self.flux_nn < 0):
            test.num_nodes = test.options.get('nn', 0)
        else:
            test.num_nodes = self.flux_nn

        # Command line option test_np_max over-rides limits the max np in the test deck
        test.np = test.options.get("np", 1)
        if self.test_np_max is not None:                              
            if test.np > self.test_np_max:      # If test np is greater than the command line max
                test.np = self.test_np_max      # then set the test np to the maxd

        test.num_nodes_calculated = 0   # Will be calculated if not specified by the user
        test.num_nodes_exclusive  = 0   # Default to 0, meaning the node is not exclusively used for each job

        if test.num_nodes > 0:                              
            # If either per test nn was specified or -nn was specified on the command line
            # then that will be used when setting test.num_nodes, and that will
            # then also be used for the num_nodes_exclusive value
            test.num_nodes_exclusive= test.num_nodes

        else:
            # If per test nn was not specified, and -nn was not specified on the command
            # then calculate the number of nodes to use based on the np (number of mpi task)
            # and the number of cpus needed per task
            total_cores_needed = test.cpus_per_task * test.np
            test.num_nodes_calculated = ceil(total_cores_needed / self.coresPerNode)

            # if --flux_exclusive option was given, then indicate exclusive node use 
            # for the job
            if self.flux_exclusive:
                test.num_nodes_exclusive = test.num_nodes_calculated

    def calculateCommandList(self, test):
        """
        Generates a list of commands to run a test in ATS on a
        flux instance.

        :param test: the test to be run, of type ATSTest. Defined in /ats/tests.py.
        """
        # ret = "flux run -o cpu-affinity=per-task -o mpibind=off".split()
        ret = "flux run ".split()

        FluxScheduled.set_nt_num_nodes(self, test)

        # If the user has given ats the --no_time_limit option, then do not
        # append the -t option at all on the flux run line.
        #
        # Otherwise set set time limit based on time limit priorities
        # 1) cuttime is 1st priority.  This will have been copied from options.cuttime into self.cuttime
        # 2) deck timelmit is 2nd priority. Check if 'timelimit' is in the test options
        # 3) --timelimit (or default timelmit) is 3rd and last
        if self.no_time_limit == False:
            if self.cuttime is not None:
                max_time = self.cuttime
            elif 'timelimit' in test.options:
                max_time = test.options.get("timelimit")
            else:
                max_time = self.timelimit

            ret.append(f"-t{max_time}")

        # If the user requests that a test be run on the same node then we store the identifying string
        # and then spread the node identifiers across the nodes we have access to. This way users dont need
        # to think about how many nodes there are or which one they want to run on.
        same_node = test.options.get('same_node', None)
        if same_node is not None:
            if same_node not in self.node_list:
                self.node_list.append(same_node)
            rel_node = self.node_list.index(same_node) % self.numNodes
            physical_node = self.get_physical_node(rel_node)
            ret.append(f"--requires=host:{physical_node}")

        """
        Need to set -n{np} and -c{test.cpus_per_task}.  But we also need to account for accessing
        GPUS using flux.  In testing flux outside of ATS it is evident that one needs to increase the -c option
        in order to access the GPUS.   The -g option alone does not suffice.
        In a test platform which has 64 CPUs and 8 GPUS, then there are 1 GPU for every 8 CPUS and the 
        -c option must be used to ensure GPU access as follows:
       
        8 MPI 1 GPU each: -n 8 -c 8   <-- each MPI rank reserves the 8 CPUS neede to get the 1 GPU
        4 MPI 2 GPU each: -n 4 -c 16  <-- each MPI rank reserves 16 CPUs to get the 2 GPUS.
        2 MPI 4 GPU each: -n 2 -c 32
        1 MPI 8 GPU each: -n 1 -c 64 
        
        Thus we need to find the 'c_multiplier' needed for each GPU.  In this case we can divide 
        the number of CPUs by the number of GPUS  (64 / 8) and get 8 as the factor. 
        And we can use this to set the -c option.

        The above is accounted for now in routine set_nt_num_nodes which was already called
        """

        # We want to limit the spread of MPI ranks across multiple nodes by flux.
        # If the user has specified a 'nn' option, we will honor that.
        # If not, determine the number of nodes needed for the job.
        # If the user specified test.nn , it also means the test should
        # have exclusive access to the node, so use --exclusive in that scenario.
        # If we calculate the -N ourselves, it does not mean exclusive access,
        # but the -N is just there to stop spreading the mpi tasks around nodes

        if same_node:   # Need to limit -N if we want to run on the same node
            if test.num_nodes > 0:   # Check that -N was set by user before giving warning
                log("ATS WARNING: Limiting nodes to 1 be able to run on same node.", echo=True)
            ret.append("-N1")
            ret.append("--exclusive")
        elif test.num_nodes > 0:
            ret.append(f"-N{test.num_nodes}")
            ret.append("--exclusive")
        else:
            ret.append(f"-N{test.num_nodes_calculated}")
            if self.flux_exclusive:
                ret.append("--exclusive")

        if test.np > self.coresPerNode and same_node:   # Need to limit cores to be the max on the node if we want to run on the same node
            log(f"ATS WARNING: Limiting cores, because of same_node option, to match max: {self.coresPerNode}", echo=True)
            ret.append(f"-n{self.coresPerNode}")
        else:
            ret.append(f"-n{test.np}")
        ret.append(f"-c{test.cpus_per_task}")   # Needs to be set properly for threaded or gpu runs

        if test.gpus_per_task > 0:
            ret.append(f"-g{test.gpus_per_task}")   # -g option allows access to GPU with mpibind turned off

        # Pass any arbitrary string provided by the user here.  This could be any of the -o options for affinity
        # preferences, or any other valid 'flux run' option
        if self.flux_run_args != "unset":
            ret.extend(self.flux_run_args.split())
            # ret.append(self.flux_run_args)

        """Set job name. Follows convention for ATS in Slurm and LSF schedulers."""
        test.jobname = f"{test.np}_{test.serialNumber}{test.namebase[0:50]}{time.strftime('%H%M%S',time.localtime())}"
        ret.append("--job-name")
        ret.append(test.jobname)
        return ret + self.calculateBasicCommandList(test)

    def canRun(self, test):
        """
        Is this machine able to run the test interactively when resources become available?
           If so return ''.  Otherwise return the reason it cannot be run here.
        """
        FluxScheduled.set_nt_num_nodes(self, test)
        if (test.np * test.cpus_per_task) > self.maxCores:
            return "Too many cores needed (%d > %d)" % (test.np * test.cpus_per_task, self.maxCores)

        if test.num_nodes > self.numNodes:
            return "Too many nodes needed (%d)" % (test.num_nodes)

        return ""

    def canRunNow(self, test):
        "Is this machine able to run this test now? Return True/False"
        sequential = test.options.get('sequential', False)
        if sequential == True:
            if self.numProcsAvailable < self.maxCores:
                return False

        # If --num_concurrent_jobs was specified
        # Throttle number of oustanding flux jobs based on this user requested limit
        # set max_outstanding_jobs as appropriate based on this logic
        if self.num_concurrent_jobs > 0:
            if FluxScheduled.flux_outstanding_jobs >= self.num_concurrent_jobs:
                if FluxScheduled.debug_canRunNow:
                    log(("FluxScheduled DEBUG: canRunNow returning False. FluxScheduled.flux_outstanding_jobs=%i >= self.num_concurrent_jobs=%i"
                        % (FluxScheduled.flux_outstanding_jobs, self.num_concurrent_jobs)), echo=True)
                return False

        # If --num_concurrent_mpi_tasks is > 0
        # Throttle ATS based on this user set limit
        if self.num_concurrent_mpi_tasks > 0:
            if FluxScheduled.flux_outstanding_mpi_tasks >= self.num_concurrent_mpi_tasks:
                if FluxScheduled.debug_canRunNow:
                    log(("FluxScheduled DEBUG: canRunNow returning False. FluxScheduled.flux_outstanding_mpi_tasks=%i >= self.num_concurrent_mpi_tasks=%i"
                        % (FluxScheduled.flux_outstanding_mpi_tasks, self.num_concurrent_mpi_tasks)), echo=True)
                return False

        if self.remainingCapacity() >= test.np:
            if FluxScheduled.debug_canRunNow:
                log(("FluxScheduled DEBUG: canRunNow returning True. capacity=%i >= test.np=%i" % (self.remainingCapacity(), test.np)), echo=True)
            return True
        else:
            if FluxScheduled.debug_canRunNow:
                log(("FluxScheduled DEBUG: canRunNow returning False. capacity=%i < test.np=%i" % (self.remainingCapacity(), test.np)), echo=True)
            return False

    # ##############################################################################################################################
    #
    # SAD : 2022 Nov 1 Comment
    #
    # The remainingCapacity() makes a call to Flux to see how many cores are available.
    # As there is a delay between ATS giving the jobs to Flux, and the actual start of the job
    # the remainingCapacity() does not reflect the jobs submitted to Flux by ATS, but rather the jobs
    # currently running.  Hence, while noteLaunch mentions that 10 cores will be requested
    # that is not immediately reflected in the return from the remainingCapacity() call. 
    #
    # ##############################################################################################################################
    def noteLaunch(self, test):
        """A test has been launched."""
        FluxScheduled.set_nt_num_nodes(self, test)

        FluxScheduled.flux_outstanding_jobs += 1
        FluxScheduled.flux_outstanding_mpi_tasks += test.np
        self.numProcsAvailable -= (test.np * test.cpus_per_task)
        self.numNodesAvailable -= test.num_nodes_exclusive
        self.numGPUsAvailable  -= (test.np * test.gpus_per_task)

        if FluxScheduled.debug_noteLaunch:
            log (   ("FluxScheduled DEBUG: After  Job Launch   "
                     "flux_outstanding_jobs=%i "
                     "flux_outstanding_mpi_tasks=%i "
                     "remainingNodes=%i "
                     "remainingCores=%i "
                     "remainingGPUs=%i "
                     "test.num_nodes=%i "
                     "test.np=%i "
                     "test.cpus_per_task=%i "
                     "test.gpus_per_task=%i "
                     "test.num_nodes=%i "
                  % (FluxScheduled.flux_outstanding_jobs, FluxScheduled.flux_outstanding_mpi_tasks, 
                     self.numNodesAvailable, self.numProcsAvailable, self.numGPUsAvailable,
                     test.num_nodes, test.np,
                     test.cpus_per_task, test.gpus_per_task, test.num_nodes)), echo=True)

    def noteEnd(self, test):
        """A test has finished running. """
        FluxScheduled.set_nt_num_nodes(self, test)

        FluxScheduled.flux_outstanding_jobs -= 1
        FluxScheduled.flux_outstanding_mpi_tasks -= test.np
        self.numProcsAvailable += (test.np * test.cpus_per_task)
        self.numNodesAvailable += test.num_nodes_exclusive
        self.numGPUsAvailable  += (test.np * test.gpus_per_task)

        if FluxScheduled.debug_noteLaunch:
            log (   ("FluxScheduled DEBUG: After  Job Finished "
                     "flux_outstanding_jobs=%i "
                     "flux_outstanding_mpi_tasks=%i "
                     "remainingNodes=%i "
                     "remainingCores=%i "
                     "remainingGPUs=%i "
                     "test.num_nodes=%i "
                     "test.np=%i "
                     "test.cpus_per_task=%i "
                     "test.gpus_per_task=%i "
                     "test.num_nodes=%i "
                  % (FluxScheduled.flux_outstanding_jobs, FluxScheduled.flux_outstanding_mpi_tasks,
                     self.numNodesAvailable, self.numProcsAvailable, self.numGPUsAvailable,
                     test.num_nodes, test.np,
                     test.cpus_per_task, test.gpus_per_task, test.num_nodes)), echo=True)

        msg = '%s #%4d %s,  nn=%d, np=%d, ngpu=%d %s' % \
            ("Stop ", test.serialNumber, test.name, test.num_nodes, test.np, test.gpus_per_task, time.asctime())

        return msg

    def periodicReport(self):
        """
        Report on current status of tasks and processor availability.
        Utilizes Flux accessors for resource_list and flux job monitoring capabilities.
        """
        # NOTE: ATS says anything that it has submitted to the queue is "running" but with Flux
        # jobs that have been submitted to the queue may not have necessarily been allocated resources yet

        if self.running:
            terminal(
                "CURRENTLY RUNNING (SUBMITTED) %d tests:" % len(self.running),
                " ".join([t.name for t in self.running]),
            )
        terminal("-" * 80)

        if self.use_flux_rm:
            resource_list = flux.resource.list.resource_list(self.fluxHandle).get()
            procs = resource_list.allocated.ncores
            total = resource_list.up.ncores
            terminal(f"CURRENTLY UTILIZING {procs} of {total} processors (Flux reported).")

        else:
            numProcsUsed = min(self.maxCores, self.maxCores - self.numProcsAvailable)
            terminal(f"CURRENTLY UTILIZING {numProcsUsed} of {self.maxCores} processors.")
            terminal("-" * 80)


    # ##############################################################################################################################
    #
    # Let's go ahead and add some throttling to Flux.  Primarily to keep down the number of open pipes used
    # to monitor jobs.
    #
    # ##############################################################################################################################

    def remainingCapacity(self):
        """Returns the number of free cores in the flux instance."""
        
        if self.use_flux_rm:

            resource_list = flux.resource.list.resource_list(self.fluxHandle).get()

            if resource_list.free.nnodes < 1:
                return 0
            elif resource_list.free.ncores < 1:
                return 0
            elif resource_list.free.ngpus < 1:
                return 0
            else:
                return resource_list.free.ncores

        # Else use ATS internal resource tracking
        elif self.numNodesAvailable < 1:
            return 0
        elif self.numProcsAvailable < 1:
            return 0
        elif self.numGPUsAvailable < 1 and self.numGPUs != 0:
            return 0
        else:
            return self.numProcsAvailable

    # ##############################################################################################################################
    # function returns TRUE if we are within a CPX allocation
    # ##############################################################################################################################
    def within_cpx_allocation(self):
        command = ["/opt/rocm-6.4.1/bin/rocm-smi", "--showcomputepartition"]

        try:
            # Run the command and capture output
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            output = result.stdout

            # Check for the presence of "CPX" in the output
            found_cpx = "CPX" in output
            if found_cpx:
                print(f"NOTICE: rocm-smi detected CPX mode")

        except subprocess.CalledProcessError as e:
            # Handle the case where the command fails
            print(f"INFO: rocm-smi failed with error: {e}")
            found_cpx = False

        return found_cpx

# end of file
