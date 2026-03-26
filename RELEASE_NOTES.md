# ATS Release Notes
    ---------------------------------------------------------------------------
##  7.0.124
    ---------------------------------------------------------------------------
Date:   Tue Mar 10 15:47:03 2026 -0700
    Fix deprecation warning (#178)

    * Fix deprecation warning
    * More backslashes

Date:   Wed Feb 25 11:23:58 2026 -0800

    Use newer numpy for python 3.13+ (#177)

Date:   Tue Feb 17 16:28:45 2026 -0800

    Reduce output for same_node setup (#175)

    * Only query nodes when inside an allocation
    * Only print node info with --verbose
    * Fix warning

Date:   Tue Feb 17 16:12:45 2026 -0800

    Fix machine entry_points logic for python 3.12+ to match 3.11.  Also … (#176)

    * Fix machine entry_points logic for python 3.12+ to match 3.11.  Also fix warning for escaping.
    * Testing with 3.13

Date:   Tue Jan 27 08:44:45 2026 -0800

    Prevent failure when running without same_node on the login node; sam… (#174)

    * Prevent failure when running without same_node on the login node; same_node should raise an exception later if running on the login node
    * Update error message

Date:   Thu Jan 22 07:48:02 2026 -0800

    Add sleep and retry before logging failed unlink (#171)

Date:   Thu Jan 15 13:37:24 2026 -0800

    same_node processing for slurm. (#172)

    However, slurm does not honor this option
    in all cases.  test23 and test24 in
    the HelloSameNode tickel this bug.

    I have tried various slurm options to get
    slurm to comply, but there are scenarios
    where it will ignore the requested node
    and just run it wherever slurm thinks
    there are free nodes.

    Thus, at this time same_node processing
    under slurm is not reliable.

Date:   Fri Jan 9 15:56:59 2026 -0800

    Fix for sameNode functionality of ATS with flux. (#170)

    Call get_physical_nodes during init.

    Need to call this immediately to cache
    the hardware nodes before any jobs
    start running. The logic inspects
    the 'free' nodes reported by flux, which
    will change during the run, so inspect
    it immediately, before starting jobs
    then save the list of hardware nodes.

Date:   Wed Dec 3 12:21:42 2025 -0800

    Adjust entry_points methods if python is 3.12 or higher (#169)

Date:   Fri Jul 18 15:25:08 2025 -0700

    Allow extra slurm arguments to be passed, allow empty partition (#168)

    ---------------------------------------------------------------------------
##  7.0.120
    ---------------------------------------------------------------------------
Date: Fri Jun 27 14:24:22 2025 -0700

    Support CPX partitioning mode on El Capitan platforms

    Purpose: Increases testing throughput by using up to 24 GPUs per node. 

    Usage: Allocate a testing partition in CPX mode (see below)
           Allow ATS to auto-detect and use 24 GPUs per node or if that fails
           allow user to specify --cpx option to force CPX mode in the allocation.

    Caveat: This feature relies on mpibind to work properly.  Do not
            pass ATS options which disable mpibind.  For instance an ATS option 
            such as --flux_run_args="-o mpibind=off" will break CPX mode. 
           
    If ats is running within CPX allocation on El Capitan machines, attempt
    to use a topological map file to properly use the 24 GPUs seen in this 
    allocation mode.   This will deliver better testing throughput.

    To allocate in CPX mode, these additional flux options may be passed
    to the flux alloc command:
    
    --conf=resource.rediscover=true --setattr=gpumode=CPX

    For projects using  Git  CI or custom ats wrappers which
    handle the allocation, the above options will need to be specified
    at the allocation time as appropriate.

    For the light weight atsflux wrapper included with ATS, the option
    --CPX may be used to allocate nodes in CPX mode.

    ATS will then, at run time attempt to detect this mode by using 
    the 'rocm-smi' executable and inspecting for CPX mode.  If detected,
    ATS will automatially set environment variables to properly use
    CPX mode as ATS submits the testing jobs. This will be reported 
    in near the beginning of ATS stdout like so:

    NOTICE: rocm-smi detected CPX mode
    NOTICE: Running in CPX mode
    NOTICE: CPX mode Setting FLUX_MPIBIND_USE_TOPOFILE to 1
    NOTICE: CPX mode Setting MPIBIND_TOPOFILE to /collab/usr/global/tools/mpi/mpibind/topo/tuo-cpx-lgpus.xml

    If auto-detection of CPX mode fails, the user may force the use of CPX
    mode by ATS by using this new ats option:

    --cpx

    In this case, look for these lines at the beginning of the ats run
    to verify CPX usage. 

    NOTICE: Running in CPX mode
    NOTICE: CPX mode Setting FLUX_MPIBIND_USE_TOPOFILE to 1
    NOTICE: CPX mode Setting MPIBIND_TOPOFILE to /collab/usr/global/tools/mpi/mpibind/topo/tuo-cpx-lgpus.xml

    This is a new feature, which likely could be extended or improved.  But for
    the purpose of better husbanding of El Capitan resources, we want to get 
    this in users hands now.

    Thoughts for future improvment currently include supporting TPX mode
    (in addtion to CPX mode), and allowing projects to specify alternative
    topo map files. 
    
    ---------------------------------------------------------------------------
##  7.0.119
    ---------------------------------------------------------------------------
Date:   Thu Jun 19 10:11:39 2025 -0700

    Update opens used for readlines. (#167)
    
    Update opens with errors='ignore' in attempt to stop the python
    coding in ATS from dying when it reads output generated by applications
    which are not utf-8 valid.  This can happen when applications print
    garbage output -- but when this happens the python in ATS breaks
    and the testing breaks.
    
    Try to simply ignore such garbage output.

Date:   Mon Mar 17 13:59:08 2025 -0700

    Add dane to slurm112 machines

Date:   Fri Mar 14 15:17:44 2025 -0700

    Update same node testing.

Date:   Fri Mar 14 14:51:55 2025 -0700

    Update list of machines which use flux natively
    with the atsflux wrapper.
    
    Set default time to 60 rather than 240 so it
    works on the various platforms.
    
    Also change version to 7.0.119 as this will be our alpha
    release we are testing.

    Find flux python correctly.

    ---------------------------------------------------------------------------
##  7.0.118 
    ---------------------------------------------------------------------------
March 12, 2025

Updates to work with updated Cray systems including tioga, rzvernal, rzadams, tenaya
Landon Owen contribution.

    Find flux python correctly.
    Added LC flux machine names, added call to include the flux python library 
    to the system path for fluxScheduled, removed rztopaz machine name
    
    Added corona to the flux machines
    Fix typo for ats util
    Fix bug with flux python path string
    Change ~= to !=

Add a general ATS machine called docker
Landon Owen contribution.
    
    Added a docker ats machine for launching tests in a more general manner

Fix wallTimeSecs() for Windows 
Ben Liu contribution
    
    Fix wallTimeSecs() for Windows
    
    Improved windows reporting

Add robustness to parsing of non-ASCII out/err files 
Ben Liu contribution
    
    Add robustness to non-ASCII output

Fix python warning in fluxScheduled.py
    
    Change
      if not self.numGPUs is 0:
    to
      if self.numGPUs != 0:
    

    ---------------------------------------------------------------------------
##  7.0.116
    ---------------------------------------------------------------------------

New Features:
    Support multiple dependencies for a job.
        Suggestion and code provided by Bob Anderson.
        Dependencies may look like the traditional still
    
        tt=testif(parent=t1, ...)

        But may also look like this using [] to specify multiple dependencies for ajo

        t1 = test(...)
        t2 = test(...)
        testif(parent=[t1, t2], ...)

    Add --quiet option to ATS.
        Will be used to suppress warnings.
        First warning to be suppressed is
        "Slurm sees ATS or Shell as itself using a CPU"

Slurm Bug Fixes:
    Fix default setting of npMax with slurmProcessorScheduled
        Use the number of CPUs reported by slurm when possible.  

    Update Slurm module to bypass setting cpus-per-task if cpus_per_task is set to 0.
        Prior to this, cpus per task was set to 1 as the minimum.  But there are use cases where
        it should actually be 0.
        

LSF Bug Fixes:
    Fix string catenation python errors in lsf_asq.py

Flux Bug Fixes:
    Fix python warning in fluxScheduled.py
        Change if not self.numGPUs is 0:
        to     if self.numGPUs != 0:

    Better support for flux timeouts


c7b94c7 (HEAD -> main, origin/main, origin/HEAD) Fix default setting of npMax with slurmProcessorScheduled
839828d Fix string catenation python errors in lsf_asq.py
97f4855 Support multiple dependencies for a job.
7240f61 Add --quiet option to ATS.
260d0ee Fix python warning in fluxScheduled.py
caafd0a Merge branch 'main' of github.com:LLNL/ATS into main
c234386 ats version 7.0.116 (beta)
36a862d Flux timeouts (#154)
d5bfb31 Update test/HelloSameNode/READ.ME
e0906ec Same_node warnings now print to console as well as log (#153)
b0a2451 New testing directory HelloSameNode
1046121 new testing
24e9d3c Same node option (#152)



    --------------------------------------------------------------------------- 
##  7.0.115
    --------------------------------------------------------------------------- 

    Issue 151: Fixed bug in LSF module where --lrun --old_defaults and mpi bind
    were not being processed correctly resulting in python error within ATS.

    Issue 149: Fixed bug in atslite1 and atslite3 where --level=10 
    (or some other number) was not processed correctly.   

    New Feature: --removeStartNote and --removeEndNote
    Implemented requested ATS command line options to reduce prints
    related to jobs starting and/or stopping.
    Requested by a project to reduce amount of messages sent to stdout.
    ATS options are:
        --removeStartNote <- will remove message notifying user of start of job
        --removeEndNote   <- will remove message notifying user of end of job

    --------------------------------------------------------------------------- 
##  7.0.114
    --------------------------------------------------------------------------- 

Commentatary on the flux run line generated by ATS.

    Different projects required different flux options.  In particular: 

        Should mpibind be on or off ?
        Should tests require excusive node access ?
        Should the cpu-affinity or gpu-affinity be set ? 

    And within a project, different test runs may also have different goals
    including:

        Throughput (shortest time to run all tests)
        Reproducibility (for performance testing, or sensitive correctness testing)
        High Memory 

    Each of these goals can be achieved with different ATS options.
    
    Since project needs vary quite a bit, ATS generates a basic flux line and then 
    provides options for projects to over-ride or append to the ATS generated
    flus run line.

    The basic flux run line which ATS generates will look like so

    flux run -t<time_limit) -N<nodes> -n<mpi_tasks> -c<cores_per_mpi_task> -g<gpus_per_mpi_task)

    ATS uses these standard, historical ATS testing options to generate the flux run line:
        nn = number of nodes
        np = number of mpi tasks
        nt = number of thread per mpi task
        ngpu / gpus_per_task = number of gpus per mpi rank
        
    And of course, there are command line options used as well, which can over-ride
    each of those options, including turning off the default per test job limit. 

Advice on running a Host compiled code using Flux

    Host Example 1: ats --flux_run_args="-o mpibind=off"

    Host Example 1 comments.  The use of "-o mpibind=off" was necessary
    in order to allow flux to pack multiple jobs onto each node, and to 
    ensure each MPI task, across all running jobs, do not share physical CPU
    cores (ie to prevent over-subscription of physical CPU cores)

Advice on running a GPU  compiled code using Flux

    GPU  Example 1: ats --test_np_max=4 --gpus_per_task=1 --flux_run_args="-o mpibind=on" 
    GPU  Example 1 comments. 

    This code uses these options to run a minimum of
    two GPU codes per node.  For tests which use less then 4 mpi tasks, this will run 
    up to 8 separate GPU jobs per node, concurrently.  The command line options explained:

    --test_np_max=4 <- sets the maximum number for the per test 'np' option. 
        if a test has np set to 1, 2, 3, or 4, then there is no change.
        if a test has np set to > 4, this --test_np_max will set it to 4.

    --gpus_per_task=1 <- Specifies that each MPI task will use 1 GPU device.   
        This is an easy way to run an existing test suite for which ngpu / gpus_per_task
        is not specified on a per test basis.  This option is equivalent to a 
        per test setting of ngpu=1, and will apply it to every test job.

    --flux_run_args="-o mpibind=on" <- This project needs to have mpibind on in 
        order to access the GPU memory using hipMalloc or Umpire.  This is an example
        of a project specific setting. 


    GPU  Example 2: --gpus-per-task=1 --flux_run_args="-o mpibind=off -o gpu-affinity=per-task"
    GPU  Example 2 comments.  

    This GPU code appears to work best with mpibnd turned off and the gpu-affinity
    set to per task.  Contact Ben Liu for more information about this example.


Added and updated Flux options:

  --flux_run_args="some string"

    This can be used to add any string that is meaningful to
    the basic 'flux run' command to each test submittal.
    For instance:

    --flux_run_args="-o gpu-affinity=per-task -o mpibind=off"

        Would add that string literal to the basic flux run line that ATS
        generates.

  --nn  
    Over-rides or appends test specific nn  option.

  --test_np_max   
    Potentially overrides the np test setting.
    That is, it limits the maximum value of np to this value.
    If the test np is less than this value, then no change
    If the test np is greater than this value, then the test np
    is reduced to this value.

    For instance if the command line option --test_np_max=4
    is used, then a per test setting of np=10 will be reduced
    to np=4.  If a per test setting of np=1 is in the test deck,
    then it will not be changed.

  --gpus_per_task  Overrides or appends the test specific gpus_per_task
        option.

  --no_time_limit

    Do not specify per job time limits on the flux run line. 
    This option takes precedence over any other timelimit or cutoff time options

  --use_flux_rm

    Use flux resource manager to detect free hardware resources.
    Default is for ATS to track available nodes, cores, and gpus.
    But there may be scenarios where calling the flux resource list
    could be useful.  

    Both should provide good throughput. 

    This information is used to know when to submit new jobs to flux.
    If a project starts seeing jobs in the flux queue (ie waiting for
    resources), one could try this alternative.

  --flux_exclusive

    Mark each job as needing exlusive access to the node.  Do not
    run multiple jobs concurrently on a node.  This option will
    pass the --exclusive option to flux on the run line, as well
    as inform ATS that each jobs needs excusive access to the node(s)
    on which it run.

  --num_concurrent_jobs NUM_CONCURRENT_JOBS
    Flux option: Limit number of concurrently running jobs. 
    Default is unset, but projects may wish to set this in 
    order to throttle ATS submission of jobs to the flux
                        scheduler.
  --num_concurrent_mpi_tasks NUM_CONCURRENT_MPI_TASKS
    Flux option: Limit number of concurrently active mpi tasks 
    across all running jobs. Default value is the number of 
    CPU cores in the allocation. Projects may wish to
    increase this or decrease this in order to throttle 
    ATS submission of jobs to the flux scheduler.

    Adjusted basic flux run line to include
    the -N option.  Used to keep flux from
    spreading MPI tasks across multiple
    nodes un-necessarily  Will use the test
    specific -nn option if specified.  If
    not specified, ATS will calculate the
    minimum number of nodes needed for the
    job and use that.
    
    Export env variable FLUX_F58_FORCE_ASCII=1,
    to tell FLUX to use ASCII characters.


    --------------------------------------------------------------------------- 
##  7.0.113
    --------------------------------------------------------------------------- 

    Better Flux support for Native Flux machines with GPUs, 
    such as rzvernal.

    Note that the MACHINE_TYPE is flux00.  You will need
    to set that in your environment (or have your ATS wrapper
    set that MACHINE_TYPE env var). 

    Note: 'flux run help' is quite useful to understand
    flux run options. 

    Removed hard coded flux options such as "-o cpu-affinity=per-task"
    and "-o mpibind=off" and "--exclusive".  These vary too much
    by project.   Please see the option flux_run_args, documented
    below, to add project specific options to the flux run line.

    Removed use of deprecated 'flux mini run', just use 'flux run' 

    Added test_np_max (see below) for flux as well as other schedulers.

    Additionally there was a change to the ATS blueOS wrapper (lsf):
        Options --lrun_np_max and --jsrun_np_max are being deprecated and
        are repaced by a single option --test_np_max to be uniform
        throughout ATS

    --------------------------------------------------------------
    P E R   T E S T   O P T I O N S

    At the individual test level, these are useful options
    when using Flux:

    Note that this release of ATS supports Per-Task flux options
    at this time.  We are considering how to add support for
    Per-resource options in the next release.
    
    nn  Number of Nodes for the test.  Translates
        to the -N option for flux and other schedulers.
    
    np  Number of MPI Ranks for the test. Translates to
        the -n option for flux and other schedulers.
    
    nt  Number of threads per MPI rank.  Will be used to set 
        the environment variable OMP_NUM_THREADS
        for the test run, as well as calculate the number of CPU
        cores reserved for each MPI rank.  This will be used to 
        set the -c flux option, which is the number of cores
        per process.

    gpus_per_task/ngpu

        The ngpu option, while still honored, is being replaced
        by the more specific gpus_per_task option.   

        Number of GPU devices per MPI Rank.  This will also be
        used to set the -c flux option in order to provide a separate
        GPU for each MPI Rank.  It is not currently used to
        set the flux -g option, as in our testing, that was
        not sufficient, nor necessary, in order to allocates
        separate GPUS for each MPI rank.

    Note that both the nt and the gpus_per_task option will 
    result in a -c option that is greater 1, which will reduce
    the number of concurrent MPI ranks that can run on a node.  This
    is by design, as ATS does not want to have concurrent tests 
    time-sharing CPUS or GPUS. 
    
    --------------------------------------------------------------
    A T S   C O M M A N D   L I N E   F L U X   O P T I O N S

    ats --help:    will show all command line options.
    flux run help: will show flux run options which may be useful
    
    Running ats with the --verbose option is an easy method
    to see the flux run line generated by ATS.

    In addition to the test level ATS options above, One may 
    use command line options to override those, or append to
    them, or to add project specific options to the flux
    run line.  

    Here are some particularly useful ATS options when using
    the flux scheduler.
    
    --flux_run_args="some string"

        This can be used to add any string that is meaningful to
        the basic 'flux run' command to each test submittal.
        For instance:

        --flux_run_args="-o gpu-affinity=per-task --exclusiive"

        Would add that string literal to the basic flux run line that ATS 
        generates.

    --nn  Over-rides or appends test specific nn  option.

    --test_np_max   Potentially overrides the np test setting. 
        That is, it limits the maximum value of np to this value.
        If the test np is less than this value, then no change
        If the test np is greater than this value, then the test np
        is reduced to this value.

        For instance if the command line option --test_np_max=4
        is used, then a per test setting of np=10 will be reduced 
        to np=4.  If a per test setting of np=1 is in the test deck,
        then it will not be changed.

    --gpus_per_task  Overrides or appends the test specific gpus_per_task
        option.  

    ------------------------------------------------------------------
    E X A M P L E   A T S   G P U   T E S T I N G   W I T H   F L U X

    As an example, here are command line settings a project used
    to run a large test suite using Flux.  While the projects ATS test
    lines already specified the np and nt options,they do not specify
    gpus_per_task. 
    Some tests have a large number for np.   The desire is
    to run on a machine which has 8 GPU and 64 cores per node.  In
    addition, the project testing goal is to achieve throughput by 
    running two concurrent jobs on each node.

    For this project the ats test run line used is:

    --test_np_max=4 --gpus_per_task=1 --timelimit=10m

    As there are 8 GPUs, this set of ATS options allows for each test to
    run with 4 MPI ranks, each of which has 1 GPU.   Thus flux should
    be able to drive two jobs concurrently on each node of the allocation.

    In addition, this project is still porting to the GPUs and there are
    some jobs which appeared to hang.   So the additionaal --timelimit
    option was specified in order to have flux kill possibly hung test 
    jobs and continue with other tests. 

    This set of options resulted in actual flux run lines, generated
    by ATS which look like so:

    flux run -t10m -n4 -c8  <etc>

    Note that the -c8 setting ensures a separate GPU for each MPI rank.


    --------------------------------------------------------------------------- 
## 7.0.111
    --------------------------------------------------------------------------- 
    Inital Flux support on Toss 4 systems where flux is 
    the native scheduler.   

    Only call 'stty sane' if ENVIRONMENT env var is INTERACTIVE
    This call results in warnings and such if in a BATCH
    environment.

    pip installs ats with poetry, not setuptools (#97)
    * pip installs ats with poetry, not setuptools
    * remove outdated bin dir files
    * rename back to atsflux

    --------------------------------------------------------------------------- 
## 7.0.105
    --------------------------------------------------------------------------- 

    Update sleepBeforeRun option.
    Renamed from sleepBeforeSrun.
    Still honor sleepBeforeSrun, simply map
    to sleepBeforeRun.
    Change value given to this option from an int to a float.
    
    Add tossrun for VIP project usage.

    Fix globalPostrunScript and globalPrerunScript processing.
    
    Strip quotes which are somehow addedd to the string in Python3
    Otherwise we can not verify the file exists or execute it.
    
    Default ruby machine type to slurm56

    For slurm:
    Account for slurm version such as 21.08.8-2
    
    Added --useMinNodes for toss (slurm)
    
    If --useMinNodes specified, then within an allocation
    specify
    
        srun_nodes="--nodes=%i-%i" % (minNodes, minNodes)
    
    when starting the job, where minNodes is the minimum
    number of nodes needed for the requested number of MPI
    processes.   This is experimental at this point,
    and may lead to hangs or lower throughput.

    For blueos:
    Add smpi options to ats command line
    
    Either one of these may be used to disable the --smpiargs="-gpu" option.
    
    --smpi_off
    --smpi_show

    --------------------------------------------------------------------------- 
## 7.0.100
    --------------------------------------------------------------------------- 

* Port to Python 3.8

    --------------------------------------------------------------------------- 
## 7.0 
    --------------------------------------------------------------------------- 

* 2021-April-19
* Migrated from Bitbucket to GitHub


