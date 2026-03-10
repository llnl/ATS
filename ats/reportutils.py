import glob
import os
from ats.atsut import INVALID, PASSED, FAILED, SKIPPED, RUNNING, \
                      FILTERED, TIMEDOUT

def findAtsrFile(testDir):
    '''Uses glob to find the atsr.py file.
    If no atsr is found in a directory, returns None.'''
    # input: path to the test directory
    # output: path to the atsr.py file in the form of a glob list.
    #  If multiple files are found, the glob list is sorted then returned.
    print("looking at %s" % testDir)
    import glob
    globList = glob.glob(testDir + '/*.logs/atsr.py')
    if len(globList)>0:
        globList.sort()
        #debug
        for g in globList:
            print(g)
        #end debug
        return globList
    else:
        return None

def getStateFromFile(atsrFile):
    '''Gets the ats state out of the atsr.py file.'''
    # input: a file (atsr.py)
    # output: the state dict
    # use case: We may want to grab something other than the test list, or
    #  make a list of state files to process
    # To get the state I'm using the example from the ats pdf, page 24 that says
    # to use execfile and rename the state, then appending it's testlist
    # to our list using the filename as it's key
    d = {}
    if os.path.exists(atsrFile):
        print("Taking state from %s" % atsrFile)
        exec(compile(open('src/ats/version.py', "rb").read(),
             'src/ats/version.py', 'exec'))
        try:
            state = d['state']
        except KeyError as e:
            print("This is a bad atsr.py file.  Skipping. %s" % atsrFile)
            return None
        # These attributes are not found in older (~2011) atsr.py files.
        # When loading the database from an archive, this was causing failures.
        if "logDirectory" in d:
            state['logDirectory'] = d['logDirectory'] # We want access to the run's logs, but they're not stored as part of the test object
        if "atsMachineName" in d:
            state['atsMachineName'] = d['machineName']   # Not sure how useful this will be, but it's available.
    else:
        print("Path does not exist.  Can't get the state for: %s" % atsrFile)
        return None
    return state

def getTestStatusLists(testlist):
    '''Returns multiple lists of test objects, according to ats test status results. '''
    # input: state or testlist...not sure if I should accept either/or or specify one.
    # output: Lists of tests according to status (passed, failed, timedout,etc.)
    passed = [test for test in testlist if (test.status is PASSED)]
    failed = [test for test in testlist if (test.status is FAILED)]
    timedout = [test for test in testlist if (test.status is TIMEDOUT)]
    skipped = [test for test in testlist if (test.status is SKIPPED)]
    filtered = [test for test in testlist if (test.status is FILTERED)]
    invalid = [test for test in testlist if (test.status is INVALID)]
    running = [test for test in testlist if (test.status is RUNNING)] # Shouldn't be any in this state because atsr.py is written after execution is done...but that may change so it's here.
    return passed,failed,timedout,skipped,filtered,invalid,running


def atsrToJUnit(atsrFile=None,junitOut=None,build=True ):
    '''Takes an atsr.py file and outputs the results in JUnit format.
       Useful for reading in test reports in tools like Jenkins or Bamboo.
       The build option is used to record passed builds - if there's an atsr.py then the build step
       likely passed.  This is included because we want to include the build logs in the
       xml file in the case that the build fails, and there needs to be a corresponding pass case
       for it to be interpreted correctly. (i.e. failed since & tests fixed are incorrect without this.
    '''
    if not junitOut:
        import time
        junitOut = "junit_"+time.strftime('%Y%m%d%H%M%S')+".xml"
    if not atsrFile:
        atsrFile = './atsr.py'
    state = getStateFromFile(atsrFile)
    passed,failed,timedout,skipped,filtered,invalid,running = getTestStatusLists(state.testlist)
    outf = open(junitOut,'w')
    # Start the xml file with needed tags
    outf.write('<?xml version="1.0" encoding="UTF-8"?> <testsuites>')
    outf.write('    <testsuite name="nightly">')
    writePassedBuild(outf)
    for test in passed:
        writePassedTestCase(outf,test)
    for test in failed:
        # You need the log dir in order to dump the .err output into the xml
        errlogpath = os.path.dirname(atsrFile)
        writeFailedCodeTestCase(outf,test,errlogpath)

    # Finish off the xml file
    outf.write('    </testsuite>')
    outf.write("</testsuites>")
    outf.close()


def cleanTestCaseName( test ):
    '''Remove all special chars from the name so it's readable to junit parser.  '''
    import re
    pattern = re.compile(r'([^\s\w]|_)+')
    testname = pattern.sub('', test.name)
    return testname

def cleanErrorMessage( msg ):
    '''Converts the text from ats .err files to strings parsable by Bamboo from within the junit.xml format. '''
    return  msg.replace('<','').replace('>','').replace('&','&amp;')


def writeFailedCodeTestCase(f, test, err_path):
    '''Writes a test failure to junit file including ats log and error files for the failure.
    '''
    # f is xml output filename
    # test is the test object
    # err_path is the path to the ats logs directory
    cname = test.name.replace('&','and')
    testname = cleanTestCaseName(test)
    f.write('    <testcase status="run" time="%.3f" classname="%s" name="%s" >\n' % (elapsedTime(test), cname, testname))

    # Write error message: Invalid chars in the .err logs cause parse errors in Bamboo (xml parse
    # errors - not Bamboo errors) so we need to handle xml special chars before writing handle the
    # case where a combined log file is written
    msg = ""
    err_files = glob.glob(os.path.join(err_path, '*' + str(test.serialNumber) + '*.log.err'))
    if len(err_files) > 0:
        with open(err_files[0], 'r', errors='ignore') as logferr:
            # not readlines() - there are standard xml escapes to fix, we don't want to iterate over
            # the whole message.
            rawmsg = logferr.read()
            msg += "***** ats log.err file: *****\nTesting branch installation\n"
            msg += cleanErrorMessage(rawmsg)
            msg += "***** END ats log.err file: *****\n\n"

    log_files = glob.glob(os.path.join(err_path, '*' + str(test.serialNumber) + '*.log'))
    if len(log_files) > 0:
        with open(log_files[0], 'r', errors='ignore') as logf:
            rawmsg = logf.read()
            msg += "***** ats log file: *****\n running from clone code \n"
            msg += cleanErrorMessage(rawmsg)
            msg += "***** END ats log file: *****\n"

    f.write('      <failure type="%s"> %s </failure>\n' % (test.status, msg))
    f.write('    </testcase>\n')


def writeSkippedTestCase( f, test):
    cname = test.name.replace('&','and') # & is reserved in xml
    testname = cleanTestCaseName(test)
    f.write('    <testcase status="skipped" classname="%s" name="%s"/>\n' % (cname, testname) )

def writeOtherStatusTestCase( f, test):
    cname = test.name.replace('&','and') # & is reserved in xml
    testname = cleanTestCaseName(test)
    f.write('    <testcase time="%.3f" classname="%s" name="%s">\n' % (elapsedTime(test),
                                                                     cname,
                                                                     test.name) )
    f.write('      <failure type="%s"> Other failure </failure>\n' % (test.status))
    f.write('    </testcase>\n')

def writeStatusTestCase( f, test, status):
    '''This case is used for those test status's other than Passed or Failed.  The status is part of the failure message. '''
    cname = test.name.replace('&','and') # & is reserved in xml
    testname = cleanTestCaseName(test)
    f.write('    <testcase time="%.3f" classname="%s" name="%s">\n' % (elapsedTime(test),
                                                                     cname,
                                                                     test.name) )
    f.write('      <failure type="%s"> ATS set test case to %s.  See ats.log for details. </failure>\n' % (test.status,status))
    f.write('    </testcase>\n')

def writePassedTestCase( f, test):
    cname = test.name.replace('&','and') # & is reserved in xml
    testname = cleanTestCaseName(test)
    f.write('    <testcase status="run" time="%.3f" classname="%s" name="%s"/>\n' % ( elapsedTime(test),
                                                                                      cname,
                                                                                      testname) )

def elapsedTime( test ):
    "Returns formatted elapsed time of the run."
    try:
        e = test.endTime
        s = test.startTime
    except AttributeError as foo:
        return (0)
    return (e-s)
