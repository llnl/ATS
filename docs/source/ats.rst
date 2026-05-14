====================
 Reference Material
====================

Test Selection and Execution
============================

Tests are defined in ATS input using two commands, ``test`` and its little 
brother, ``testif``. However, not every test that gets defined is necessarily
going to be executed. The user can define logical conditions (*filters*) that
a test must satisfy to be chosen for execution, and the hardware available may
cause others to be skipped.

In order to make it easier to structure suites of tests, there is an elaborate 
set of facilities involving filters, command-line options, and arguments to
``test`` statements, as well as facilities for grouping and ordering your test
executions. 

ATS Execution and Command-line Options
--------------------------------------

.. index:: input file names

In specifying the names of input files, you can give the filename or omit 
the filename extension. ATS will attempt to find the file
using its name, then with a ``.ats`` extension, and then with a ``.py`` extension.

.. index::
   pair:execution;ATS

Unix or Mac
~~~~~~~~~~~

To start ATS on a Unix system or Mac, execute this line in a terminal 
window::

    ats [options] [input files]

Note that the ``--exec`` option is frequently used to define a default 
executable, but any given test can specify any executable as the program to be 
tested.

Before executing ATS, it may be desirable to have defined the environment
variables MACHINE_TYPE and / or SYS_TYPE; and there may be others for testing
particular executables. Please consult with the owner of your local ATS 
installation, and the owners of any custom ATS drivers you may be using.

Windows
~~~~~~~
Execution on windows can be done in the same way from a command window, but
can be made more convenient by defining a ``.bat`` file, such as::

   C:\python27\python c:\python27\ats $*

These instructions need improvement as the first Windows users determine 
the right way to do this.

Command-line Options
~~~~~~~~~~~~~~~~~~~~

.. index::
   pair:command-line options;ATS
   pair:command-line options;list 
   pair:command-line options;using --help

What follows are the the most important command-line options available in any 
ATS installation. 

.. note::
   The exact set of command-line options depends on the machine you are using 
   and / or upon any custom driver you are using for testing a particular 
   program.  To see the complete list for a given ATS installation, enter 
   ``ats --help``.

   This will also show you abbreviations for some of the options.

--allInteractive
   Run every test in interactive mode.

--cutoff cutofftime
   Over-rides the timelimit for all jobs no matter where the timelimit is set. Jobs
   that fail once reaching the cutoff will TIMEOUT. The forms for giving the time
   are the same as for ``--timelimit``. Note: Jobs that TIMEOUT are marked as FAIL
   when using Flux.

--debug
   Debug mode; prints more information in the log and on the shell window.

--exec EXEC
   Give the path to the code to be tested.  The path is tilde- and 
   dollar-expanded.  

   This option sets the environment variable ATSROOT, if not already set, 
   to the directory in which the executable resides.  Most of the time
   this option is used, and the executable so named is referred to
   in this documentation as the `specified executable`.

   However, tests with different executables can also be specified, by using the
   executable='/path/to/my/code' as one of the test options. The purpose of 
   ATSROOT is to allow you to specify related tools for your code that are 
   located in the same directory as the executable. In specifying a test, you 
   can use this variable in the script or executable using either `$ATSROOT` 
   or `%(ATSROOT)`. 

   Note that you don't have to have one main code to be tested. 
   You can specify a different executable for each test, or group of tests.

--filter FILTER
   Add a filter; may be repeated.  Be sure to use quotes if the filter contains 
   spaces and remember that the shell will remove one level of quotes. 

--glue FILTER 

  Has the effect of executing `glue(FILTER)` before execution of the tests. 
  May be repeated. Be sure to use quotes if the filter contains spaces and 
  remember that the shell will remove one level of quotes.
  The glue function is used to set persistent test option defaults.

--help 
   Show the list of options and exit. There may be more options than are 
   shown in this document, such as batch or node control options.

--info 
   Print information about ATS, such as version, path to the executable, 
   and some parameter values.

--keep
   Keep the output files from the tests that succeed.
   Normally the output from tests that fail, or which must be checked, is kept.

--logs LOGDIR
   Sets the name of the log directory.  The default log directory is 
   `arch.time.logs`, where arch will be an architecture-dependent name, and 
   time will be digits of the form `yymmddhhmmss`. All logs and the 
   continuation file are placed in this directory. The log itself is named
   `ats.log`.

--level LEVEL
   Set the maximum level of test to run. Level is simply a built-in easy-to-use 
   filter.

--skip 
   Skip actual execution of the tests, but show filtering results and missing 
   test files, and show additional details about the input.

--nobatch
   Do not run any "batch" tests..

--nosrun
   Run the code without srun. This option can also be used on BlueOS to run ALL test on
   a login node as it circumvents the login node check. If the tests need to be run on
   a working node, then the tests themselves will need to get an allocation.

--npMax value
   Value is an integer, the maximum number of tests to run at once (on a node, 
   if multinode machine).  Some machines allow you to set this higher than
   the actual number of nodes, at your own risk.

--okInvalid
   Run tests even if there is an invalid test. Examples are tests specifying 
   missing scripts or executables.

--oneFailure
   Stop if a test fails.

--removeStartNote
   Removes the messages printed at the start of a test running.

--removeEndNote
   Removes the message printed at the end of a test running. Will still get results
   printed with pass/fail, just no "stop".

--serial
   Run only one job at a time.

--timelimit TIMELIMIT
   Set the default ``timelimit`` test option. TIMELIMIT may be given as an 
   integer number of seconds or a string specification such as '2m', or 
   '3h30m20s'. A similar notation can be used for filtering by time limit, such 
   as `-f 'timelimit < "30m"'`. Note: Jobs that TIMEOUT are marked as FAIL
   when using Flux.

--verbose
   Verbose mode. Both starts and finishes of tests are noted on the terminal, 
   plus other reports. Test failures are reported regardless.

--version
   Show program's version number and exit.

Basic Operations
----------------

The goal of ATS is to execute a series of test problems.  It does this by 
reading input files written in the Python language, with some predefined ATS
functions added. In particular, ATS supplies a function named ``test``. Each
execution of the ``test`` statement defines a particular program to execute,
including its command line and a variety of options used by ATS to know
how to run it or to decide not to run it. 

After running the tests, the ats prints a summary of which tests have passed 
(that is, returned with a normal exit status) and which have
failed. 

The second basic statement is the ``source`` statement, which causes a
file to be read containing additional commands. An introspection
procedure, described below, is also available to allow scripts meant as
problem input to contain definitions of how they are to be run when run by
ATS.

Retrying Failed Tests
~~~~~~~~~~~~~~~~~~~~~

If any tests fail or are not completed, a "continuation" file is written and 
a message issued in the summary section giving the name of the file. 
The continuation file is named continue.ats and it is inside the log directory. 

You can rerun the exact same ATS command, adding the path to the continuation 
file as an extra command-line argument.  

.. note:: You must run the *exact* same command with this added argument at 
   the end of the command line.

Doing this will redo those families of tests that had a failed member. 
This process may be repeated until all tests pass. In your log, tests that
had passed before well be marked "Previously passed" and batch jobs will be 
"skipped".  The continuation file is pretty self-explanatory and you can edit 
it with thought.

Note that if a descendent of a test failed, the test will be rerun because the 
error might have been in files produced by the parent test, even though it 
appeared to pass.

The intention of this facility is to let you fix your code without having to 
rerun all your tests.  For correctness, you should rerun everything once you 
believe you have corrected all errors.

.. _Results_Facility:

.. index:: post-processing file

Results Facility
~~~~~~~~~~~~~~~~

Each run creates an ``atsr.py`` file in the log directory. This file, if
run under Python, creates one variable named "state", which is an
object that is a dictionary whose values can be read and written using 
either dictionary or attribute notation. This type is called an 
AttributeDict.

The object state has attributes corresponding to the major features of 
the manager object, including a ``machine`` and ``testlist``, which is
a list of AttributeDicts, each encapsulating the major properties of
each test.

Two methods in the manager object control this facility, which may 
be used by custom drivers.

.. function:: onSave(saver)

   Registers a ``function saver(results, manager)``, which will be called
   when the data for the state is collected. It may modify the 
   AttributeDict ``results`` in any way it likes, usually by adding to it.
   Calling ``results.clear()`` would be a way of minimizing the use 
   of resources devoted to this file.

   onSave is available in the test environment also, for use in input 
   files. Note that the call does not cause the save of the file at the
   time it is executed. 

Three other manager methods can be called from custom drivers.

.. function:: getResults()

   Returns the AttributeDict containing the state. The manager's 
   ``machine`` and, if set, ``batchmachine``, are given a change to
   contribute fields to the end result, and finally any onSave-registered
   routines are called in the order they were registered.

.. function:: saveResults(filename="atsr.py")

   Save the state to a file using given file name; if not absolute,
   put it in the log directory.

.. function:: printResults(file=sys.stdout)

   Do the actual job of writing the state file. Here file should be an open  
   file handle. You would only use this function if you wanted to add
   something to the file other than the ``state`` variable.

Normally ``saveResults`` creates the file and asks ``printResults`` to
call ``getResults`` and print the returned state into the file, preceded 
by a header that imports the symbols in the ``ats`` module so that the code 
will execute correctly.

Interactive inspection of the resulting file is most easily accomplished 
with an interactive Python session, such as::

    cd <logdirectory>
    python -i atsr.py
       print "Number of tests = ", len(state.testlist)
       print "Machine name", state.machine.name
       print "Number timed out", \
             len([t for t in state.testlist if t.status == TIMEDOUT])

Note that ATS statuses will compare equal if they compare to another 
status or the name or the abbreviation. So in the last line above, 
TIMEDOUT, "TIME", or "TIMEDOUT" would all work. 

To compare different files you can rename state as you read it::

    d= {}
    execfile("atsr.py", d)
    state1 = d['state']

.. index::
   pair:saveFileName;``atsr.py``

You can change the name of the file to be used by setting manager.saveResultsName
in your input file. If not an absolute path, the file will be created in the logs 
directory.
    
.. _Input:

Controlling Input
=================

File Sourcing
-------------

.. function:: source(*paths, **vocabulary)

   Process one or more paths as if each was the name of an
   input file given on the command line. (This function is the same as 
   manager.source)

   The current stuck options are saved upon entry, cleared before beginning
   processing, and then restored on completion.  See `stick` below
   for further details.

   Path names are expanded both for tilde and environment-variable
   names using the dollar sign.

   The vocabulary items can be any number of keyword = value pairs. 

   Vocabulary words are added to the environment in which input files are 
   compiled by Python. The scope of this environment is just within the input of
   the paths given to this source command. To add a vocabulary value to all 
   subsequent source commands, use the `define` command, described next.

   The vocabulary word *introspection* can be used to change the commenting
   convention used for ATS' introspection facility.  Details are given below.

.. function:: define (keyword=value, ...) 

   adds one or more keywords to the vocabulary used by the source command to 
   parse input.  This is the same function as manager.define.

.. function:: undefine(keyword, ...) 

   removes one or more keywords from the vocabulary used by the source command 
   to parse input. This is the same function as manager.undefine.

.. function:: showDefine(*keywords, **options) 

   logs the current definition of one or more keywords in the vocabulary used by
   the source command. If no argument is given, all the definitions are shown. 
   This function is used to help debug your vocabulary setup. The options may 
   include echo and logging, and are passed on to the call to log. The defaults 
   are both True. This is the same function as manager.showDefine. 

A file may be 'sourced' because it was given on the command line or
because a ``source`` function was executed with it as an argument. (Note: In 
what follows it is is assumed that a line that starts `#ATS:` is a comment to 
your application; however, it is possible to change the commenting convention to
suit your input convention, using the second argument to ``source``.

.. index::
   triple:onCollected;input;customization

Examining and prioritizing tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After collection of the tests the user may wish to examine or alter the
tests before they are executed.  This is done by registering one or more 
routines to be called (in the order in which they were registered) by using
``onCollected``. See also ``onPrioritized``, below.

.. function:: onCollected (routine)

The routine registered is called when the input is complete. It is given the
manager object as its single argument.  The routine thus has access to the
``manager.testlist``.  

The routine may make use of the routine that ATS itself is about to use to 
divide the tests into interactive and batch tests::

   interactiveTests, batchTests = manager.sortTests()

You can effect what happens next by changing statuses (such as setting the 
status to BATCH or FILTERED or CREATED (i.e., interactive)) or change
``totalPriority`` (see below).

You also have a chance at this point to use each test's ``directory`` attribute 
to prepare the file system, or to build data structures for later use in a postprocessor.

Use this facility with caution. Do not attempt to change tests that would 
not have executed at all into ones that will. If you change a label it must be unique when you are done. Do not alter serial or group numbers.

.. index::
   triple:onPrioritized;input;customization

After the ``onCollected`` actions, the scheduler prioritizes the interactive 
tests. The ``totalPriority`` attribute of each test is set to the sum of the 
test's own value plus the sum of the priorities of each test that must wait 
for this one to complete. (Such conditions are created by dependencies or
``wait`` or ``group`` commands.)

The user may wish to examine or alter the priorities of the tests
tests before they are executed.  This is done by registering one or more 
routines to be called (in the order in which they were registered) by using
``onPrioritized``.

.. function:: onPrioritized (routine)

The routine should take a single argument, interactiveTests. The intent is for
the user to examine or alter the ``totalPriority`` attribute of a test.
Altering ``priority`` attributes will not work.  Altering anything else about
the test is probably ill-advised.

In summary, there are two ways to change the ``totalPriority`` attribute:
in an ``onCollected`` routine, which will contribute the new value to its 
predecessors, or in an ``onPrioritized`` routine, where you are setting the
final absolute value.

.. index::
   single: introspection

Using Introspection
-------------------

.. index::
   triple: ``#ATS:``; input; introspection

When a file is sourced, ATS looks to see if the file contains any
lines that begin with the five characters `#ATS:`. If so, the set of
such lines with the leading `#ATS:` removed will be executed as Python
code. The remainder of the file will be ignored. This procedure is called 
*introspection*.

Note that Python's indentation rules apply, so there should not be any
spaces after the `#ATS:` except on lines that should be indented.

For example, continuation of lines is allowed in the normal Python
manner::

   #ATS:test('myfile.py', 
   #ATS:     'my command line args',
   #ATS:     np = 4)

Picture the first five characters as defining the
left edge of the lines to be executed.

.. index::
   single: SELF

During this procedure, the symbol SELF will be defined to be the name
of the file being sourced. Thus a line such as::

   #ATS:test(SELF, 'command line options', np=4, w=2)

will cause the file to be tested with the given command line, using
the options np = 4 and w = 2 as context for filtering. 

A file may contain many such lines, in order to exercise the same test
with a variety of parameters. Also note that not all the `#ATS:` lines
need to be ATS commands; they can be any Python code.  They can also
include log commands, source other files, etc.

Changing the introspection convention
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. index::
   pair:introspection;changing comment convention

If a value for the vocabulary word "introspection" is given, it should 
be a python function which, when given a line, returns None or the value 
of the line as introspection. The default is a function that returns None
unless the line begins with `#ATS:`, in which case it returns the line 
less that prefix.

By prescribing your own value for introspection, you can allow the 
introspection process to work on source files with a different commenting
convention than "#". 

In particular, to change the default function used for introspection, just use 
define after you declare it. For example::

   def asteriskinterpolation(line):
       "Any line that starts with *ATS: is magic"
       if line.startswith("*ATS:"):
           return line[5:]
       else:
           return None
   define(interpolation=asteriskinterpolation)

.. index::
   single:preventing conflicts
   single:tests with postprocessors
   pair:options;group
   pair:option;independent
   pair:option; report

.. _group_statement:

Grouping
--------

If you have a test that creates some files for postprocessing, you can group that 
test with the related ones.

You begin with:

.. function:: group (independent = False, report = False, **kw)

and after defining some tests, finish with:

.. function:: endgroup()

A group is also ended by another group statement, or the end of the current input file.
The arguments to the ``group`` call become default options for each test defined 
inside the group. They can be overridden by options in the ``test`` and ``testif`` 
statements within the group.

Only the first test result will be included in the final reports unless some member of 
the group fails, or you change the report argument to True. The output files 
of the entire group will be kept if anything fails; otherwise the usual keep options
will prevail. 

The ``independent`` test option determines if a test will block any other test (other than 
ones in its group) that uses the same directory. By default, then, a group
will lock-out any non-independent test or group from running in the directory or 
directories its tests use. This is not different than the default behavior of ATS, 
but is a convenience for making sure that the members of the group will not be 
interleaved with other, non-independent tests that use the same directories, if you
have glued or tacked or stuck independent to be be True. 

These two arguments are used as test options for all tests in the group, but for any
particular test can be overridden by an explicit option in the test statement itself.

Note that grouping does not make each test depend on the preceding tests in the group.
Two members of the group may execute together. It also does not make the failure of
one test skip another. To achieve dependency, use the 'testif' facility.

.. index::
   pair:wait;statement
   single:preventing conflicts

Wait
----

It is certainly possible to make two tests that appear to be independent but which 
cannot in fact run simultaneously. ATS prevents many cases of this due to its reluctance
to run two tests in the same directory at the same time. If that fails to solve the 
problem, and the ``group`` or the ``testif`` statements are not sufficient, you can try
the ``wait`` statement:

.. function:: wait()

   All the tests defined so far in this source file will be finished
   before proceeding to any tests defined later in this source file.  Tests 
   defined in other files that are sourced *after* the 'wait' must also wait
   for all the tests before the wait in this source file. 

wait() may be a useful way to express massive dependencies without using 
excessive `testif` calls.  However, if used excessively, `wait` may cripple 
ATS's ability to run tests simultaneously.

You can debug your wait structure with this command::

   ats yoursource --skip

This will show a list at the end of the log file, under "ATS RESULTS", 
showing the serial numbers being waited for by each test.

When all tests are completed, ATS issues a final report and runs any 
postprocessors that have been registered using the `onExit` facility described
later.

Example
~~~~~~~

Suppose we have this test file "waitforit.ats"::

   glue(executable = "/bin/ls")
   test(label='first')
   test(label='second')
   wait()
   test(label='third')

Then the third test will not execute until the first two are done -- but this says 
nothing about the order in which the first two will execute.

Suppose now we add a source of another file, so we have::

   glue(executable = "/bin/ls")
   test(label='first')         #1
   test(label='second')        #2
   wait()
   source('waitfor1.ats')
   test(label='third')         #6

with the file being sourced containing::

   test(label='waitfor1 first')   #3
   test(label='waitfor1 second')  #4
   wait()
   test(label='waitfor1 third')   #5

We have thus defined six tests in all. The output of the debugging process is::

    Interactive tests:
    #1 INIT ls(first) ready
       []
    #2 INIT ls(second) ready
       []
    #3 INIT ls(waitfor1 first) ready
       [1, 2]
    #4 INIT ls(waitfor1 second) ready
       [1, 2]
    #5 INIT ls(waitfor1 third) ready
       [1, 2, 3, 4]
    #6 INIT ls(third) ready
       [1, 2]

The parts in square brackets are lists of the tests this one must wait for.
(The list will include any tests of which this one is a dependent.)
So we see for example that ``#6``, the last test in the main file, waits for the
first two tests, because a ``wait()`` occurs after ``#2``, but it is
not affected by the wait statement in the sourced file.  In that file 
the first two tests are waiting for the first two, and the third waits for
the first four.

Executing Tests
===============

ATS attempts to execute as many tests as it can at the same time in order to keep
the computational resources it has been given busy, subject to respecting the 
test options ``priority`` and ``independent``, and the ``group`` and ``wait`` statements.
The following sections describe this process.

.. _scheduling:

Scheduling
----------

.. index::
   pair:priority;scheduling
   pair:totalPriority;scheduling
   pair:scheduler;scheduling 
   pair:scheduler;standard

After the ATS has read all the input and knows what tests are to be run,
it examines the collection and combines the information generated by the *group*,
and *wait* commands with the test dependencies to figure out which tests must 
execute before others. It can then combine the priorities of tests to determine a
preferred order of execution -- which however will be subject to processor availability.

This work is done by a scheduler object. A standard scheduler is provided, and is an 
attribute on the ``machine`` object. A user could potentially modify it by inheritance from
its defining class, ``schedulers.StandardScheduler``.

.. index::
   pair: test option; priority
   pair: test attribute; totalPriority

Each test has a priority. By default the scheduling priority (``totalPriority``) 
is the number of processors required by the test plus the priorities of any tests which 
cannot execute until this one is finished. In this way those tests with a lot of dependents 
are started early.

A test may specifiy its priority as an option "priority=n" where n is a nonzero integer.
A test whose priority is zero or less will not be run. Thus, a long-running 
1-processor job without dependents might profit from being given a priority, 
say 3, so that it starts earlier. Note that an np = 0 job requires 1 processor.

.. index::
   single: independent (test option)
   pair: test option; independent
   pair: test option; priority
   pair: test attribute; totalPriority
   pair: test attribute; runOrder
   pair: test attribute; groupNumber
   pair: scheduling; influences on

As tests are selected to be started, the highest-priority job that will fit on 
an available machine is chosen.  You can examine the tests in postprocessing if you want 
to understand what influenced the scheduling:

* Test option priority,
* Test attribute totalPriority, 
* Test attribute group,
* Test option independent (described below)
* Test attribute runOrder, an integer indicating the order of test launch.

.. note::
   Important: by default two non-independent tests will not be run in the same
   directory at the same time.  See
   :ref:`directory blocking <directory_blocking>` for the full rule.

This is a modestly conservative scheme to avoid common resource conflicts when
testing one file with different parameters.  If you know a test does not have
such a problem, you can give it the option ``independent = True``.

The standard scheduler sorts the groups by the highest priority test in the group. In effect,
every member of a group behaves as if it has the priority of the highest-priority test in the 
group. This ensures a large prejudice towards running members of a group once it has started,
until they are all complete.

.. index:: --verbose

Progress Reports
----------------

When a test starts this fact is shown on the terminal output. You can use the command
option ``--verbose`` to cause test completions and other additional events to be reported
as well. All the information is always in the log. Additional output is generated by
the ``--debug`` option.

Every minute ATS issues a report on its progress to the terminal only.

.. index:: --keep

.. index::
   single: output files
   pair: tests; output files
   pair: output files; disposition of
   pair: test option; keep

Output Files
------------

The standard output and standard error of a test are written into 
files in the directory where the logs are written.  These files are (usually) 
removed when the test concludes successfully; for a group, this occurs when *all*
members of the group have succeeded. 

The name and label of the test script or executable, along with the test's 
serial number, are used to create the file names.

The --keep option prevents the removal of these output files even when
the tests are successful. They are also kept if the test has the option 
keep=True or check=True.

.. seealso::
   Postprocessors set using the `onExit` facility can access the magic output
   of a test as test.outputats. 

.. index::
    single: killing jobs
    single: control-C
    single: interrupts
    pair: RUNNING; status

Interrupting a Run
------------------

A control-C interrupt will terminate the program and all the tests it
is running. Any test started but still not finished will be reported
in RUNNING status.

Creating and Selecting Tests
============================

.. index:: test creation

.. _testFunction:

Creating Tests
--------------

.. function:: test(*args, **options)

   This notation means that you can give positional, unnamed arguments, 
   followed by keyword=value arguments. 

    * If you give just one positional argument, it is called "script". 

    * If you give two, they are "script" and "clas".

    * If you do not give one or both positionally, they are given in the 
      options, with their default values being blank strings.

    It is an error to give more than two positional arguments. 

   Positional arguments are allowed for backwards compatibility -- it is 
   preferable to name everything.

.. index::
   pair: test statement; script
   pair: test statement; clas

In the test function call:

 * script is a file name, which may be be relative to the directory containing 
   the input file or absolute.  Note that ATSROOT can be used in such names to 
   designate either a preset environment value or the directory of the specified
   executable. The script if given will be used as the first argument on 
   the test's command line, and will supply a default name for the test.

 * clas is a string giving the command-line arguments to be passed
   to the execution. Before doing so, python string interpolation is used
   with the options dictionary. This means, for example, that::

      test(clas = "-in %(input)s -parallelism %d", np=4, input='foo')

   will result in::

      clas = "-in foo -parallelism 4"

You might want to do this if, for example, this expression for clas was 
constant over many tests except for these variations of input and np. Then
you could stick or glue this value for clas and not have to repeat it over 
and over.

Options can be any keyword = value pairs declaring the properties
of this particular test; these are used in filtering and also
serve as documentation for the test's properties.

.. index:: test statuses

test returns an test object whose attribute 'status' is one of the
following attributes of the ats module: CREATED, RUNNING, HALTED,
PASSED, FAILED, TIMED, FILTERED, SKIPPED, BATCHED, INVALID.

.. warning:: Testing the truth value of a test object, such as using it in an 
   `if` clause, causes the test to be marked FAILED. See `testif` below.

The test object will execute in the directory `test.directory`. This value can
be set in the test options, but if it is not (which is usually the case)
it is set to the directory in which the script resides, if the script is given.
Otherwise it is set to the directory in which the test statement was read.

Note that if executable is 1, the script isn't really a script, so directory
is set to the directory in which the test statement was read. 


.. function:: testif(othertest, *args, **options)

   This is the same as the test statement except that this test will only be 
   run if ``othertest`` is eligible to run, has been run, and has been 
   successful.

For example::

   t = test('foo.py', 'dumpat=25')
   testif(t, 'foo.py', 'restartat=25', label='restart test')

Explanation: This works because the test call returned a test
object, ``t``. 

Expecting Failure
~~~~~~~~~~~~~~~~~

.. index:: ~ operator

.. index:: expecting failure

Sometimes you want to make sure a test will fail. To do this use the tilde (~)
operator on the test::

    ~test(....)

The test will count as passed if its status ends up FAILED.

You can also set the ``expectedResult`` attribute of the test directly to something
other than PASSED::

    t = test(....)
    t.expectedResult = TIMEDOUT

It is pointless to have a dependent of a test that is not expected to PASS.
It will be SKIPPED.

Test Options
------------

.. index:: test option overview

Each test can define arbitrary keyword = value pairs. With the exception
of a few special options described below, the keyword names are arbitrary. 
Most options do not affect the running of the test, just the decision
about whether or not to run it.  

There are five lifetimes of option specification: 

 * defaults (often with command-line options to change the value), 
 * permanent (see glue and unglue), 
 * current and descendent files (see tack and untack)
 * per sourced file (see stick and unstick), and 
 * per test (using the options portion of the test command).

Reserved option names
~~~~~~~~~~~~~~~~~~~~~

.. index::
   single: test options

.. index::
   pair:label;test option
   pair:name;test option
   pair:np;test option
   pair:exécutable;test option
   pair:batch;test option
   pair:check;test option
   pair:keep;test option
   pair:independent;test option
   triple:independent;directory blocking;groups
   pair:priority;test option
   pair:env;test option
   pair:magic;test option
   pair:SYSTEMS;test option
   pair:hideOutput;test option
   pair:record;test option
   pair:timelimit;test option


While you are free to use any desired scheme for options and filters,
do not use the following names except for the purposes described.
These are listed roughly in the order of their frequency of use by the 
end user.

label 
   label can be set to a string that will be appended to
   the name of the test to identify the test more fully. Thus, two
   different runs of the same script can be distinguished. 
   label by default is the test's serial number, the number that distinguishes
   the order in which the test was defined. labels are adjusted after all
   tests have been read to add distinguishing characters, so that no two tests
   have the same label.

name
   This is the test name, as is printed out in the summary. If a script
   is given, it is that file name less the extension. Otherwise it defaults
   to the base name of the executable.

np
   The option 'np' is reserved for specifying the number of
   processors to be used to run the program if the machine is
   a parallel processor. np = 0, the default, means a scalar
   run. np = 1 will be treated as a serial run on serial computers.
   np can be used in filters, e.g. `np < 32`.

executable
   This option sets the path to the program to be run for this test. The 
   default value of this option is usually set by the --exec
   command line option.

   The executable program will be
   considered to have passed or failed depending on its exit status.

   The executable may contain options after the path; it may also be given
   as a list of strings, the first component being the path and the rest 
   options.  If the path contains an internal space, you must use the 
   list form.

   .. deprecated:: If executable is 1, the first positional argument to the 
      test function is the name of the executable program. It is preferable
      to use `executable = /path/to/executable`.

batch
   This option is used to run a test in batch by setting it 
   equal to 1 or True. Note that the filter `batch` (which you can set with 
   the --filter batch command-line option) will restrict 
   submissions to only batch jobs and the remaining non-batch jobs
   are skipped.

check
   If check is not zero, this test is marked to be
   checked by hand rather than marked as passed, if it finishes
   normally. Such jobs are reported separately in the summary.

keep
   If true, the test's output files are kept even if it passed.

.. _directory_blocking:

independent
   If ``independent`` is True, the user is certifying that there is no obstacle
   to this test executing at the same time as any other test.  Otherwise, by
   default tests are assumed to conflict with other non-independent tests in the
   same directory, because they might write files there with the same names as
   those read or written by other tests.

   ATS implements this with a directory block.  A test's block is normally its
   execution directory.  When a non-independent test starts, its group owns that
   directory block.  Another non-independent test or group using the same block
   cannot start until the owning group's non-independent members have finished.
   Other members of the owning group may continue to run under that block.

   The ``group`` command makes the default value of ``independent`` False for
   all members of the group, overriding anything except an explicit option in
   the test statement.  If you do not want this behavior for the group, pass
   ``independent=True`` to ``group``.

   Judicious use of ``independent=True`` will increase ATS's throughput.  Use
   it only when tests in the same directory do not share output files, generated
   inputs, cleanup patterns, or other directory-local state.

priority 
    By default the priority of a test is np + the sum of the priorities of
    and dependent jobs. The priority option lets you override this by giving
    an integer value. A value of zero means the test will be skipped.

env
    By default the environment passed to the test will be the value of the ATS
    environment ``os.environ``. To modify this dictionary, give the option env=D,
    with a value D that is a dictionary of the additions or changes to environment
    variables that you desire. If None, or not given, the default is used.

record
   If a test is given option record=False, it is not reported as a separate 
   test unless it fails in some way.

timelimit
   Specifying a timelimit denotes maximum execution time for the test.
   For example, timelimit="30m" will kill the test after 30 minutes 
   and give it TIMEDOUT status.

SYSTEMS
   SYSTEMS defaults to a list of one value. That value is the value of the 
   "name" attribute of the machine object ATS has discovered. A filter::

      s in SYSTEMS 

    where s is this same value, is always used. Thus, by specifying SYSTEMS as 
    an option, the test will run only on the machines(s) named in SYSTEMS.  

magic
   magic controls the treatment of certain lines of test output.
   The default value is ``#ATS:``.

   If a test prints any lines beginning with the characters `#ATS:`,
   those lines will appear verbatim in the output, but also will be
   printed, less the `#ATS:` prefix, in the summary messages that
   appear when the test finishes.

   If magic is set to None or a blank string, the entire parsing of the output 
   file is skipped. 

hideOutput
   If true, do not print magic output lines in the log.

same_node
   ONLY WORKS ON FLUX (ATS can run Flux under slurm). Specify a string identifier
   for the tests that you want to be run on the same node. Useful for tests that
   depend on some data output by another test that might not be accessable from
   other nodes. NOTE: Using this option will limit -N 1 and -n to max on one node,
   if more than that were requested. Ex: same_node='abc'

Extra Arguments On The Executable
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. index:: executable

If you want to always execute a given application with some fixed arguments in
addition to others that vary, you may give them as part of the executable option
to a test or on the command line.  For example::

    my_application = "/foo/bar -a -b"
    test(clas="-d", executable=my_application)

will result in the execute line ``/foo/bar -a -b -d``.

Be careful about quoting levels. For example, to make a test that did the 
equivalent of::

    python -c "print '3+4'"

you must use an extra quotation level::

    my_application = "python -c"
    test(executable=my_application, clas = "\"print '3+4'\"")

Filters
-------

.. index:: filters

A filter is a string that can be evaluated to a logical result.  Filters can
be defined with the command line option -f or --filter, or using the 
function `filter`. Helper functions can be defined using
`filterdefs`.

Each test declares options: these are keyword = value pairs.  To
decide whether or not to execute a test, each filter is evaluated
using Python's eval function, in an environment consisting of these
symbols:

 * The options set by the test (including current 'stuck', 'tacked', and 
   'glued' option values described below) 

 * Symbols created parsing of text added by calls to filterdefs.  

 * The ats environment, consisting of these
   objects, which are each described in this document::

      manager, test, testif, source, log, filter, filterdefs, stick, unstick, 
      tack, untack, glue, unglue, 
      getGlue, getTack, getStick, sys, os, AtsError, AtsTest, abspath, 
      is_valid_file, is_valid_executable, statuses, 
      CREATED, RUNNING, INVALID, PASSED, HALTED,
      FAILED, BATCHED, SKIPPED, FILTERED, 
      SYS_TYPE, MACHINE_TYPE, MACHINE_DIR, BATCH_TYPE,
      onExit, onSave, getResults.  

 * SELF is equal to the test object and some of its attributes
   may be interesting for filtering (name, label, basename).

If the filter returns true when evaluated, the test will be run.
Otherwise, or if the filter gets a NameError when evaluated, the test
will not be run.

Thus, a test run with::

   test('mytest.py', x = 7) 

would pass the filter 'x==7' but not pass the filter 'x==5' nor the filter 
'y==7' (because the symbol y is not defined by the test).

Additional ATS Vocabulary
-------------------------

ATS input is written in a expanded dialect of Python. That dialect
contains the following facilities.

.. index:: vocabulary

Debugging and logging
~~~~~~~~~~~~~~~~~~~~~

.. index::
   pair:--debug;command line options

.. function:: debug ([value = None])

   debug() can be called in your input; it will return the current debug level:
   zero if --debug was not specified, or one if it was. 

   You can give debug an argument to set a new value, such as debug(2), and 
   issue conditional code depending on the value which is returned by debug().

.. index:: log output
.. index:: terminal output

.. function:: log(*items, [echo=False, logging = True])

   The log written by ATS, and the terminal (in the form of stderr), can also 
   be written to from user input. The log function adds a line to the log, 
   using the enumerated items as if in print statement, unless logging is 
   False.  If echo is True, it prints to standard error.

   With no items log prints a blank line.

   For example::

      log("I want to eat", 5, "donuts")

   prints::

      I want to eat 5 donuts

.. function:: terminal(*items)

    This is a version of ``log`` that writes only to the terminal.

Other methods and attributes in the log object are:

.. function:: log.indent() 

   Increase the current indentation.

.. function:: log.dedent() 

   Decrease the current indentation.

.. function:: log.reset() 

   Reset indentation.

.. attribute:: logging 

    A switch that controls logging to file

.. attribute:: echo

   A switch that controls logging to stderr.

Shortly after it gets organized, log sets the defaults for logging and echo.
To be SURE you write something to stderr, use echo=True. And if you change 
logging or echo, or the indentation level, put things back as you found them,
please.

It is not possible to log a partial line.

Manipulating Test Options
-------------------------

.. index::
   pair: test options; manipulating
   pair: options; test
   pair: options; glued
   pair: options; tacked
   pair: options; stuck
   pair: options; group
   pair: options; in test or testif statement

The following facilities provide for setting more-or-less persistent default 
values for test options.  Each type listed will override the ones above it 
while it is still in scope.

 #. A default value for most options is built in to ATS.
 #. Command-line options override the default.  Command-line options are not 
    available for every test option, just the most important ones.
 #. glued: Values set with a `glue` call. Such values apply until overridden
    by another glue call.
 #. tacked: Values set with a `tack` call. These values apply until processing
    of the current file is finished, including in files sourced by this one.
 #. stuck: Values set with a `stick` call. These values apply only in the
    file in which the call appears.
 #. group: Values set with a `group` call. Such values can be overridden by an
    explicit value in the test. Group values last until the next ``group``
    or ``endgroup``, or the end of the source file. 
 #. explicit: Options given in a `test` or `testif` call always apply to
    that test. 

Great care should be used with glued and tacked options, because they are not 
visible locally in files that are later sourced "from above", and a person 
working on one of these files may not realize they are inheriting a value 
already that will take effect unless they override it. This will also cause the file 
to behave differently if used stand-alone as opposed to sourced from 
another file.  Use the least scope that will get the job done for you.

Putting tests in groups has other consequences you should be aware of. 
See in particular :ref:`directory blocking <directory_blocking>`.

Here are the functions for controlling test option defaults:

.. function:: stick(**keys)

   Add the keyword = value pairs to the current dictionary of stuck test 
   options. Stuck options persist until the end of the current file but do not
   apply in files sourced from this one.
 
   A stuck option overrides a tacked or glued option, and is in turn overridden 
   by an explicit option to ``test`` or ``testif``.

.. function::  tack(**keys) 

   Add the keyword = value pairs to the current dictionary of tacked test 
   options.  Tacked options persist until end of the current file and do
   apply in files sourced from this one.

   A tacked option overrides a glued option, and is in turn overridden by a 
   stuck value or by an explicit option to ``test`` or ``testif``.

.. function:: glue(**keys)

   Add the keyword = value pairs to the current dictionary of glued test 
   options. 

   Glued options apply to all subsequent test definitions.  A glued option can 
   be overridden by a stuck or tacked option, which in turn can be overridden by
   a value given in a test or testif statement.

    Think of glued options as permanent changes to the default value
    of an option. One use might be to be sure every test has a value for
    some option name so that a filter can be constructed.

Notice the language here carefully. In the following example, the value which
will be used in the test for the option color is "blue"::

   stick(color = "blue")
   glue(color = "red")
   test("myscript", clas = "%(color)s")

The stuck option overrides the glued one of the same name. 

Items can be removed from these dictionaries with:

.. function:: unstick(*names)

   Remove each name from the list of stuck options. If no list is given, remove 
   all the stuck options.

.. function:: untack(*names) 

   Remove each name from the list of tacked options. If no list is given, remove
   all the tacked options.

.. function::  unglue(*names)

   Remove each name from the list of glued options. If no list is given, remove 
   all the glued options.

Filters are constructed with:

.. function:: filter(*filters)

   Add each string argument as a filter. With no arguments, delete all existing 
   filters. Note that if you attempt to filter using the name of an option
   for which you have not set a default using the facilities above, then 
   any test in which the option is not specifically set will be not be executed.

   Each ``--filter`` command-line option is simply a call to this function.
   
   The command-line option --skip allows you to test your filters without 
   executing any tests.

To assist you in constructing filters we have:

.. function:: getOptions() 
 
   Return a dictionary of the options as they would be seen by a test
   defined at the location of this call. Intended to aide debugging of options.

.. function:: filterdefs(text=None)

   Add result of parsing text to the filter environment.  Usually used to add 
   functions to use in filters. If text is None, clear the environment.

Despite the power available here, we recommend you don't get too cute about it.
The main thing is for it to be clear what is happening.

Customization
-------------

.. _Customization:

The Andyroid Tutorial contains ideas on various sorts of customization.
These include defining your own postprocessor, main program, and 
application-specific input language extensions.

Using Levels
------------

.. index:: levels

.. index::
   triple: level; --level; stick

To use levels, make a master.ats file with stick commands separating the 
tests, such as this example input::

   stick(level=10)
   test("test1.py")
   test("test2.py")
   
   stick(level=20)
   test("test3.py")
   test("test4.py")
   t5 = test("test5.py")
   
   stick(level=30)
   test("test6.p7")
   
   # this test sets a level explicitly, that overrides the "stick".
   testif(t5, "test7.py", level=10)

The currently "stuck" value is set in every test that does not explicitly set 
level. Thus test3, for example, has level 20, as if the level=20 were given in 
the test statement.

Executing ats on this file with the option --level 30 will execute all these 
tests. Executing ats with --level 15 will execute only test1 and test2; test7 
depends on test5, which has level 20, so it will not be run even though it has 
level 10.

The Test Class
--------------

When a test is created by the test or testif command, a test object representing
it is added to manager.testlist.  This object is an instance of a class named
``AtsTest``.  Some users may wish to use the following details for debugging
or postprocessors or customization.

The class ``AtsTest`` is available to users as ``ats.AtsTest``.

.. class:: AtsTest(*args, **options):

   .. data:: stuck, glued, tacked 

      These are the current dictionaries for determining test options.

   .. data:: test_number

      The counter showing the number of tests defined so far.

   .. attribute:: serialNumber

      The unique serial number of this test.

   .. attribute:: name

      Set from an option to the test creation, or as the name of the script,
      or the name of the executable, plus the label. Eventually each test's 
      name is made unique.

   .. attribute:: label

      Set from an option to the test creation, incorporated in the name
      if given.

   .. attribute:: options

     The options for this test, after resolution using defaults, stuck, 
     tacked, and glued.

   .. attribute:: depends_on

      If not None, the test instance this one depends upon.

   .. attribute:: dependents

      A list of any direct dependents of this test.

   .. attribute:: exited

      Has the job been run and exited?

   .. attribute:: output

      A list of lines of magic output, newlines and magic removed

   .. attribute:: notes

      List of notes from the run; user feel free to append to this list.  

   ..attribute:: level

      Test level set from resolved options. Same as ``options.level``.

   .. attribute:: np

      Number of processors required. Same as ``options.np``.

   .. attribute:: batchDic

      A dictionary that may contain various things for a batch job.

   .. attribute:: clas

      A string containing the command line arguments after option interpolation.

   .. attribute:: executable

      An Executable object specifying the executable's full path.

   .. attribute:: directory

      The full path to the directory in which the test is executed.

   .. attribute:: groupNumber

      The number of the group to which this test belongs, if positive.

   .. attribute:: groupSerialNumber

      The number of the test within its group definition.

   .. attribute:: outname

      The path to the standard output file for the test. 

   .. attribute:: errname

      The path to the standard error file for the test. 

   .. attribute:: message

      Explains the current value of ``status``.

   .. attribute:: runOrder

      A number indicating the order in which the interactive tests were run.

   .. attribute:: shortoutname
      
      An abbreviated form of ``outname`` used for labeling.

   .. attribute:: timelimit

      An object of class Duration -- ``timelimit.value`` is the limit in 
      seconds. Duration objects can be compared to integer numbers of 
      seconds correctly.

   .. attribute:: waitUntil

      A list of serial numbers of tests this one must wait for.

   .. attribute:: nosrun

      Boolean value, runs the code without srun when ``True``. This can also be
      used to circumvent the login node check so that a test can be run on a login
      node. When used it will be up to the test to get an allocation if needed.

   .. method:: set (status, message)

      Set the object's status and message.

   .. method:: elapsedTime()

      Returns a string, the formatted elapsed time of the run.

   .. classmethod:: stick, unstick, glue, unglue, etc.

      Class methods stick, unstick, glue, unglue, etc. are 
      equivalent to the ones accessible in the vocabulary or ats module.

There are other methods that are not intended for end users.

Test Statuses
~~~~~~~~~~~~~

There are eleven status values that a test can have. This value is stored in the 
test's attribute ``status``. Collectively this set of a statuses is in the
list ``ats.statuses`` and each of them individually is in module ``ats``.

Each status has a four-character abbreviation, shown in parentheses. The status can also be 
accessed under this name in the ats module. For example, PASS and PASSED are the same 
object. You can correctly compare two statuses using "is" or "is not", ``==`` or ``!=``,
or compare a status to a string representing its name or abbreviation, as in 
``PASSED == "PASS"``.

.. index::
   single:test statuses
   pair:status;BATCHED
   pair:status;CREATED
   pair:status;EXPECTED
   pair:status;FAILED
   pair:status;FILTERED
   pair:status;HALTED
   pair:status;INVALID
   pair:status;PASSED
   pair:status;RUNNING
   pair:status;SKIPPED
   pair:status;TIMEDOUT

The statuses are:

INVALID (INVD)
   The test was not properly stated. For example, it referred to a script file 
   that did not exist. See the log file for the error.

CREATED (INIT)
   The test was created but not (yet) run. 

PASSED (PASS)
   The test was run and succeeded.
 
FAILED (FAIL)
   The test was run and failed.

EXPECTED (EXPT)
   The test ran and failed in an expected way.

TIMEDOUT (TIME)
   The test ran longer than its timelimit and was killed.

SKIPPED (SKIP)
   The test was created successfully but skipped for some reason.
   The reason is in the test object's attribute ``message``.

FILTERED (FILT)
   The test was created successfully but filtered out for some reason.
   The reason is in the test object's attribute ``message``.

BATCHED (BACH)
   The test was deemed eligible for batch processing, and has been shipped off 
   to the batch system. ATS does not know its fate.

RUNNING (EXEC)
   The test is running, or was running when an error or keyboard interrupt 
   occurred.

HALTED (HALT)
   The test was stopped after running successfully for one minute. This status
   is only possible if the ``--cutoff`` command-line option is used.


Postprocessing
--------------

.. index:: postprocessing

After ATS has finished executing tests, but before it exits, it calls any 
Python routines that have been registered with it by calling::

    manager.onExit(routine)

The routine should have the signature 
::

   def routine (manager):
   ...

The routine can do anything it wants. In particular, manager.testlist is 
available. Here's an example of a trivial postprocessor in an input file::

   def routine(manager):
      passedTests = [test for test in manager.testlist \
              if test.status is manager.PASSED]
      print [test.name for test in passedTests]
   manager.onExit(routine)
   source ("set1.ats")
   source ("set2.ats")

The postprocessing file is designed to make it possible to run postprocessing functions
of this kind using the ``state`` variable as the ``manager`` argument, rather than
doing it as an ``onExit`` routine.

Test Suite Strategies
---------------------

.. index::
   pair: test suite; organization

One of the problems with excessive choice is the paralzying effect of choice. 
There are a lot ways to do things with ATS. So here we describe a 
basic strategy to use until you have enough experience to form your own opinion.

We strongly urge that you read the Andyroid Tutorial as well.

This scheme assumes your code sources are destributed over a set of directories 
with a common parent called Home, with a subdirectory Test. 

In each subdirectory with code that has a separate test (such as a unit test, 
or a test that emphasizes that coding) put a file with extension "ats". This 
file contains a series of source statements that get further input or are test 
inputs containing introspective test statements).

::
   test(clas = "-in myinput", np = 1)
   source("mysubdir/moretests.ats")

Separate these inputs into levels with stick-level statements such as:: 

   stick(level = 10)
   ...some tests...
   stick(level=20)
   ...longer-running tests...
   stick(level=30)
   ...still more...

You choose how many different levels you like. We recommend choosing well-spaced
numbers in case you later change your mind and want to insert levels between the
ones you start out with. Note that any test can still specify a level on its own
that would override the stuck level.

As you go up your directory tree toward Home, put files that source the ones 
below it, until finally you have a tree leading to a file, say "testsuite.ats", 
residing in your Home/Test directory.

Then you can make a series of small drivers. For example, your shortest test 
suite my be driven by this file::

   glue("level <= 10")
   source("testsuite.ats")

Running ats with this file as its input will result in only tests with level 10 
or less being executed.

When the team that maintains a certain area wants to add a test, they add it 
to the closest member of the test-file tree relative to the source code they 
work with. They put it in the file at the appropriate level. This scheme leads 
to only rare source-code control conflicts, and ones that are usually a trivial 
merge; this avoids the conflicts generated by having a central test file.  

Teams should be encourage to use introspection so that other members, less 
informed about how to test a certain area, can nevertheless exercise a good 
suite of tests using ATS, while allowing the experts to still use the input file
directly with the code. 

If there is one principle program being tested, it makes sense to use the 
-e option for it, and only explicitly specify an executable when it is 
different. 

::
   mycode = '/full/path/to/my/code'
   test(executable=mycode, script='foo.py')

The extended example in Examples/Andyroid gives you many more ideas about how 
to use ATS.

Porting and Custom Machines
===========================

.. index:: porting to new machine types

.. index:: customized machines

.. index:: SYS_TYPE

.. index:: MACHINE_TYPE

.. index::
   pair:customized machines;adding test options

.. _Porting:

ATS decides on which machine characteristics to use by examining the value of 
the environment variable MACHINE_TYPE; or, if it is not defined, the value
of the environment variable SYS_TYPE; or as default the value of Python's 
``sys.platform`` variable. 

The reason for this three-level structure is to allow you to distinguish 
machine architectures when you have machines of the same basic type but with
varied environments such as current OS level, parallel processing directives,
or attached hardware. For an ordinary user on a personal computer, there is no 
reason to do anything special.

Most of the interaction between ATS and the platform takes place in
a machine module, defined by default in the sources in file ``Lib/machines.py``.
Different behaviors are obtained by inheriting from this module, or one 
derived from it, and overriding various methods. We then connect our new
machine module to a value for MACHINE_TYPE with a comment in our module file,
and install that module in a directory in the Python distribution.

Porting ATS to a new platform is just one of the things you can do
with the technique we describe in this section; you can also do things like 
doing something special when a job finishes, inventing your own scheduling 
algorithm, etc. You'll need a decent knowledge of Python to do it, but
you don't need to be an expert.

If you invent a new value for MACHINE_TYPE, you can change the way ATS launches 
and finishes jobs and keeps track of resources, amongst other things. You can 
add command-line options and react to the user's use of them. Your options will 
even appear when the user executes with ``--help``.

To do this, you write a new Python source file, usually having a module name 
equal to your value for MACHINE_TYPE.  This file must define a new child of 
``machines.Machine``, and you must have a comment::

    #ATS:name module class npMax

This line or lines defines the relationship between a MACHINE_TYPE and this 
module's machine class and provides the maximum number of jobs you wish to 
execute at once (or it may mean the maximum number of processors one job can 
use in a parallel programming environment):
   
* name is the name to match with MACHINE_TYPE.
* module is the name of the module file, or SELF.
* class is the name of the class in that module to use as a Machine.
* npMax is a limit on np; if this number is negative it is a suggested 
  default only.
* ``machine.scheduler`` is created by the standard ``__init__`` method  of 
  the machine. If you want to create your own scheduler you can replace this 
  attribute. See :ref:`Customizing the Scheduler <StandardScheduler>` below.

The file ``Lib/machines.py`` is well documented and it is usually not a large 
problem to get things working. 

.. index:: 
   :pair:installation;setup.py

Once you have your module file ready, you write a setup.py file to go with it::

   from distutils.core import setup
   myMachines =[myMachine.py]   # list your machine module files
   setup(name="myAtsAddon",
        author = "you",
        version = "1.0",
        description = "All About My Machine",
        data_files = [('atsMachines', myMachines)],
        scripts = ['mycustomdriver'],  #if you have one
   ) 

and then execute ``python setup.py install``. Set the environment variable 
MACHINE_TYPE and run ATS. It will report the machine module it has discovered.

In this ``setup.py`` file, the unchangeable word is ``atsMachines``. This
is the name of a directory below your Python installation root where the
machine files are found by ATS.  The scripts line can be omitted if you 
do not want to install your own driver. 

Installing Machines as Plugins
------------------------------

As an alternative to the ``data_files`` approach you can register custom machines
with ATS using setup tools' entry points plugin mechanism.  This may be convenient
if you are building more customized ATS wrappers that are themselves packages, but
can also be used on standalone plugin packages. In this install method, ATS will look for
these in the group ``"ats.machines"``.  This entry point name space is required for ATS
to find your machine plugin.  The example below shows how to set this up with a
``pyproject.toml`` build system using setuptools::

  ...
  
  [build-system]
  requires = ["setuptools", "wheel"]
  build-backend = "setuptools.build_meta"

  ...

  [project.entry-points."ats.machines"]
  custom_slurm_proc_sched = "mywrapper.atsMachines.myAtsSlurmProcessorScheduled:MyAtsSlurmProcessorScheduled"

This shows adding a ``custom_slurm_proc_sched`` machine that's defined in the parent
wrapper ``mywrapper``'s atsMachines submodule, where the ``MyAtsSlurmProcessorScheduled``
class is defined in ``myAtsSlurmProcessorScheduled.py``. This makes the machine name
``custom_slurm_proc_sched`` available to ats to use to instatiate a new machine.  With
this case you can either write whole new machines from scratch, or inherit from one
of the default machines to change it's behavior.  For more details see the setuptools
documentations, which also includes more how-to's for ``setup.py`` and ``setup.cfg`` based
packages.

Note one major difference with this method currently: the default machine config is not
read from the ``#ATS:name module class npMax`` comment.  The name, module and class gets
read in from the plugin info, but the ``npMax`` field is not set.  It defaults to -1
in this case; the current convention is to use env vars to override it inside the machines,
so be sure and set those accordingly when configuring your custom machines.
   
Adding Test Options Via Machine
-------------------------------

In a customized machine, the ``examineOptions`` routine can add entries to 
a dictionary, ``options.testDefaults``. These will be default option values for each
test.  For example, here is how you would add an option ``nt`` that could
be specified on the command line in the machine file::

   def addOptions(parser):
       parser.add_option('--nt', dest='nt', default=1, type='int',
           help='Set default number of threads per test.')

   def examineOptions(options):
      options.testDefaults['nt'] = options['nt']

Of course, the machine would also have to examine and use properly the value of
each test's option ``nt``; but it would always have one, and hence it could be
used in filters.

Customizing the Scheduler
-------------------------

The scheduler class StandardScheduler is defined in module ``schedulers``. It
handles issues such as priorities, and enforcing rules for the ``group()`` 
and ``wait()`` commands, and the ``independent`` option.

Customizing the scheduler is possible but difficult. It should in particular 
supply a method testlist() that returns the list of tests that are not yet
completed. Inheritance is strongly suggested, so that you only change what 
you need to change. You'll probably want to change the machine too so that
it creates the correct scheduler, but it feasible to create and assign a new
machine attribute ``scheduler`` at any point up to and including the call to 
``machine.load``.

The important thing is to maintain correct separation between the scheduler 
and the machine objects. The scheduler must ask the machine for such things 
as ``canRunNow`` that are within the purview of the machine, and ask it 
about whether jobs have finished. The machine contains an attribute ``running``,
a list of the jobs currently running.  The ``periodicReport`` in the 
scheduler does the basic report once a minute; a machine can call this and 
then add more.

The ats Module
==============

The ``ats`` module can be imported in custom drivers and postprocessors.
Resources available in it are all imported from internal modules.
These are documented further in the Appendix.

.. function:: log, terminal

   See the discussion of the log. ``terminal`` is simply a version of ``log``
   that only writes to the terminal, not the log.

.. attribute:: times

   Is a module containing useful time-handling routines

.. attribute:: configuration 

   Is the module that has information about the machine and command-line
   options.
 
.. attribute:: manager

   Is the manager object. It has in particular ``testlist``, and the 
   routines discussed above. It is defined in the ``management`` module.

.. attribute:: testEnvironment   

   Is the vocabulary dictionary.

.. attribute:: AtsTest

   Is the test class.

.. function:: debug(value = None)

   Is the debug function

.. exception:: AtsError 

   Is the class of exceptions thrown by ATS.
 
.. attribute::  statuses, CREATED, INVALID, PASSED, FAILED, HALTED, SKIPPED, 
                BATCHED, RUNNING, FILTERED, TIMEDOUT, SYS_TYPE, MACHINE_TYPE

   Discussed previously, these are available via the ats module as attributes.

.. _StandardScheduler:

.. index:: 
   pair: StandardScheduler;customizing

Using A Batch Facility
======================

General Information
-------------------

.. index:: batch

.. index:: BATCH_TYPE

When running ATS, if a batch facility exists, both the interactive jobs and 
batch jobs will run.  You have to use the facilities of that batch facility
to find out what happened to those tests, because ATS will likely finish and
exit long before those jobs are done.

Unfortunately, the world doesn't have a standard batch facility. So here is
an example of using the MSUB batch system at the Livermore Computing Center.
Much of what follows would apply to any batch system.

To add a different batch system one must customize a batch machine to be
installed in your ATS. For advice on how to do this, please contact us.

The basics are simple: if a test has a ``batch = 1`` option, it is a batch test.
Each of the batch tests are individually submitted to the batch system.  
The ``--allInteractive`` flag is available to execute such tests without using
the batch system. Otherwise, they are simply skipped if no batch system is
found.

For the LC system in particular, 

* A *testName*.bat file is craated for the test.
* The test information is written to a "batchContinue.log".  This file will be 
  a concatenation of all the batch tests and will provide information about 
  the tests.

Running Entirely In Batch
-------------------------

Submitting a lot of single batch jobs may overwhelm some batch systems.
In that case it may be preferable to submit just one big batch job.
One batch job is created to run all the tests (both batch and interactive).  

The ATS option ``--allInteractive`` is neccesary in the ATS command to prevent 
the tests from being submitted seperately as batch.

An example of a batch script using MSUB at LC::

   #!/bin/csh
   
   #MSUB -N tmpAts0.157456004499.job
   #MSUB -j oe
   #MSUB -o tmpAts0.157456004499.job.out
   #MSUB -q pbatch
   #MSUB -l nodes=4:ppn=16
   #MSUB -l ttc=64
   #MSUB -l walltime=200
   #MSUB -V                    # exports all environment var
   #MSUB -A myBank             # bank to use
   
   setenv SYS_TYPE chaos_4_x86_64_ib
   
   date
   cd /my/work/directory/; atsb --allInteractive --numNodes=4  -useSrunStep Test/full.ats
   date
  
The command-line options ``--numNodes=4 --useSrunStep`` are not a part of 
standard ATS. In this case, the ATS machine type ``chaos_4_x86_64_ib`` has been 
defined in a custom machine file, and custom machine files can add command-line options.
 
More Examples
=============

.. index::examples

.. index::introspection

Introspection
-------------

::

 mytestA.py:
   #ATS:test(SELF, batch=1, np=2, ...)
   ...mytestA problem...
   
 mytestB.py:
   #ATS:stick(batch=1)
   #ATS:test(SELF, ...)
   ...mytestB problem...
   
 myAts.ats:
   tack(batch=1)
   source('mytestC.py')
   source('mytestD.py')
   source('mytestE.py')

In ``myytestA.py``, a 2-processor batch job is created by introspection.

In ``mytestB.py``, the test created through introspection will be run in batch,
unless it happened to explicitly contain the option batch = 0, because the
``stick`` call makes batch = 1 the default in this file.

Running ``myAts.ats``, the ``tack`` makes batch = 1 apply also in the three 
files that get read. If this were a ``stick``, it wouldn't apply inside those 
other files.

Test Control
------------

.. index:: filters

Suppose the file mytest.py contains a test script. The script
throws an exception if it gets an error. It has a command line
argument delta. Suppose mytest.py reads::

   #ATS:log('mytest.py tests sanity of my group leader.')
   #ATS:test(SELF, 'delta=0.5')
   #ATS:test(SELF, 'delta=0.6', sanitycheck = 1)
   #ATS:test(SELF, 'delta=0.7', np=4, sanitycheck = 1)
   import physics
   ...command line processing to get delta's value...
   ...test problem....  
   ...throws an exception if it fails...

If we run::

   ats --exec myapplication mytest.py

then it is equivalent to running 3 tests::

   myapplication mytest.py delta=0.5
   myapplication mytest.py delta=0.6
   myapplication mytest.py delta=0.7

The last one is run on 4 processors if the machine supports it.

Consider the command line::

   ats --exec myapplication -f 'sanitycheck == 0' mytest.py

None of the tests are run; the first because sanitycheck is not one
of its options, the other two because it is but the value is not
zero. We could make sanitycheck have a default value of zero for all tests 
in mytest.py by adding this line to the top of mytest.py::

   #ATS:stick(sanitycheck=0)

With this line added we would run only the first test.

Using the filter sanitycheck==1 would run the last two tests but
skip the first. Using the filter 'not np' would run only the first
two jobs, since they have by default np == 0.

Suppose mytest.ats reads::

   source('mytestA.py')
   source('mytestB.py')

and mytestA.py reads::

   #ATS:stick(batch=1)
   #ATS:test(SELF,delta=0.1)
   ...mytestA problem....  

and mytestB.py reads::

   #ATS:test(SELF)
   ...mytestB problem....  

.. index::nobatch

If we run::

   ats -e myapplication --nobatch mytest.ats

then only myTestB.py is executed, and execution of mytestA.py is skipped,
since ats is not set for batch tests to run. Note ``--exec`` can be abbreviated
as ``-e``.

If we run::

   ats -e myapplication mytest.ats

then mytestA.py is submitted to batch and mytestB.py is run interactively.
If there is no batch system, mytestA.py is skipped.

In practice a batch facility, if present, would add further options for 
controlling itself, such as options to set accounts or priorities or timelimits.
The maintainers of such batch facilities will provide the documentation for 
them.

Finally, 
::

   ats --allInteractive -e myapplication mytest.ats

will test both myTestA and myTestB.

Resources For Learning ATS
--------------------------

The `Examples` directory in the distribution contains the sources that
accompany the Andyroid Tutorial, including some sample customizations.

The `Test` directory contains more examples, although care 
must be taken in reading them as some of these are designed to fail.

At your particular location you may find other directories that define
machines and batch systems for your local computer center.

Quick Recipes
-------------

* To run only the batch tests::

   ats --filter 'batch == 1'  mytest.ats

* To run only the interactive tests::

   ats --nobatch  mytest.ats

* To run all tests as interactive tests::

   ats --allInteractive mytest.ats

* To check your input add --skip; add --debug for even more information.
* To keep the output files even if the test succeeds, add --keep

