import os, sys, time, getopt, socket, re
from ats import atsut
from stat import ST_SIZE

#*********************************************************************


def showq(label=None,node=None,user=os.environ['LOGNAME']):
# showq examples:
# activeJobs: showq -r
# JOBID S PAR EFFIC XFACTOR Q USERNAME ACCNT MHOST NODES REMAINING STARTTIME
#
# eligibleJobs: showq -i
# JOBID PRIORITY XFACTOR Q USERNAME ACCNT NODES WCLIMIT CLASS SYSTEMQUEUETIME
#
# blockedJobs: showq -b
# JOBID USERNAME STATE NODES WCLIMIT QUEUETIME
#
# completedJobs: showq -c
# JOBID S CCODE PAR EFFIC XFACTOR Q USERNAME ACCNT MHOST NODES
# WALLTIME COMPLETIONTIME
    if label == 'active':
        opt = 'r'
    elif label == 'eligible':
        opt = 'i'
    elif label == 'blocked':
        opt = 'b'
    elif label == 'completed':
        opt = 'c'
    else:
        opt = ''

    if opt:
        cmd = 'showq -%s -u %s'%(opt,user)
    else:
        cmd = 'showq -u %s'%user

    host = socket.gethostname().split('.')[0]
    node2runCMD = host

    pipe = os.popen(cmd)
    lines = pipe.readlines()
    status = pipe.close()

    allJobs = {}
    if status is not None:
        print()
        print('cmd=%s' % cmd)
        print('status=%s' % status)
        print('lines=%s' % lines)
        if status == 32512:
            print('ATS ERROR: showq command not found: status=%s' % status)
            print('       cannot execute showq command from %s' % node2runCMD)
            sys.exit(1)
        elif status == 256:
            print('Failed to run showq command with status=%s. Retry' % status)
            if label is None:
                # lists active, eligible and blocked jobs
                allJobs['active'] = {}
                allJobs['eligible'] = {}
                allJobs['blocked'] = {}
            else:
                allJobs[label] = {}
            return allJobs
        else:
            print('ATS ERROR: failed to run showq command with status=%s' % status)
            print('       executed showq from %s' % node2runCMD)
            sys.exit(1)

    if lines:
        if label is None:
            # collect active, eligible and blocked jobs
            jobs = {}
            for linen in lines:
                line = linen[:-1]
                line = line.strip()
                if not line:
                    pass
                elif line.startswith('active jobs-----'):
                    label = 'active'
                elif line.startswith('eligible jobs---'):
                    label = 'eligible'
                elif line.startswith('blocked jobs----'):
                    label = 'blocked'
                elif line.startswith('JOBID'):
                    pass
                elif line.find('%s job'%label) > -1:
                    allJobs[label] = jobs
                    words = line.split()
                    num_jobs = int(words[0])
                    if num_jobs != len(jobs):
                        print('num_jobs=%s; len(jobs)=%s' % (num_jobs,
                                                             len(jobs)))
                        print('ATS ERROR: num_jobs != len(jobs)')
                        sys.exit(1)
                    else:
                        jobs = {}
                elif line.startswith('Total job'):
                    pass
                else:
                    # active job has line: "... 1571 of 2448 nodes active ..."
                    if line.find('nodes active') > -1: continue
                    words = line.split()
                    jobID = str(words[0])
                    jobs[jobID] = words[1:-4] + [' '.join(words[-4:])]

            return allJobs

        else:
            jobs = {}
            for linen in lines:
                line = linen[:-1]
                line = line.strip()
                if not line:
                    pass
                elif line.find('%s jobs----'%label) > -1:
                    pass
                elif line.startswith('JOBID'):
                    pass
                elif line.find('%s job'%label) > -1:
                    words = line.split()
                    num_jobs = int(words[0])
                    if num_jobs != len(jobs):
                        print('num_jobs=%s; len(jobs)=%s' % (num_jobs,
                                                             len(jobs)))
                        print('ATS ERROR: num_jobs != len(jobs)')
                        sys.exit(1)
                elif line.startswith('Total job'):
                    pass
                else:
                    # active job has line: "... 1571 of 2448 nodes active ..."
                    if line.find('nodes active') > -1: continue
                    words = line.split()
                    jobID = str(words[0])
                    jobs[jobID] = words[1:-4] + [' '.join(words[-4:])]

            allJobs[label] = jobs
            return allJobs

    # lines == [] and status == None: not possible
    else:
        print()
        print('showq(label,node,user) returned lines==[] and status==None')
        print('label=%s; node=%s; user=%s' % (label, node, user))
        print('status=%s; lines=%s' % (status, lines))
        print('not possible. exiting')
    return allJobs






def realHostName(host):
    if host == '' or host is None:
        print('host name is None or empty')
        return None

    host0 = host.lower()
    #if host0 in nodeMapping.keys():
    #    return nodeMapping[host0]
    #else:
    #    return host
    return host

def getBaseHostName(hostname):
    "get base host name without digits"
    host = realHostName(hostname)
    # get non-digit part of node name
    wordpat = re.compile(r'(^[a-zA-Z_]*)(\d*)').search
    basehost = wordpat(host).group(1)
    return basehost


def checkJob(jobID,basenode=None):
    cmd = 'checkjob %s'%str(jobID)
    host = socket.gethostname().split('.')[0]
    basehost = getBaseHostName(host)
    node2runCMD = basehost
    job = {}
    pipe = os.popen(cmd)
    lines = pipe.readlines()
    status = pipe.close()
    if status is not None:
        return job

    if lines:
        for linen in lines:
            line = linen[:-1]
            line = line.strip()
            if not line:
                pass
            elif line.startswith('job'):
                key,jid = line.split()
                if jobID != jid:
                    msg = 'jobID=%s; jid from checkjob command=%s.'%(jobID,jid)
                    #print 'ERROR: %s Terminated'%msg
                    return job
                job['jobID'] = jid
            elif line.startswith('AName'):
                key,jobname = line.split(':')
                job['jobname'] = jobname.strip()
            elif line.startswith('State'):
                key,status = line.split(':')
                job['status'] = status.strip()
            elif line.startswith('Completion Code'):
                line0 = line[len('Completion Code:')+1:]
                line0 = line0.strip()
                if line0.find('Time:') == -1:
                    job['Completion Code'] = int(line0)
                else:
                    lst = line0.split('Time:')
                    job['Completion Code'] = int(lst[0])
                    EndDateTime = lst[1].strip()
                    EndTime = EndDateTime.split()[-1]
                    EndDate = EndDateTime[:-(len(EndTime)+1)]
                    job['EndTime'] = EndTime
                    job['EndDate'] = EndDate
                    job['EndDateTime'] = EndDateTime
            elif line.startswith('Creds'):
                lst = line.split()
                for word in lst:
                    if word.startswith('Creds') or word.startswith('qos'):
                        pass
                    else:
                        # user:name1, group:name2 and account:name3
                        key,val = word.split(':')
                        job[key] = val
            elif line.startswith('WallTime'):
                lst = line.split()
                job['WallTime'] = lst[1]
                job['timelimit'] = lst[3]
            elif line.startswith('SubmitTime'):
                datetime = line[len('SubmitTime: '):]
                lst = datetime.split()
                time = lst[-1]
                date = datetime[:-(len(time)+1)]
                job['SubmitDate'] = date
                job['SubmitTime'] = time
                job['SubmitDateTime'] = datetime
            elif line.startswith('IWD'):
                j,job['testdir'] = line.split()
            else:
                # ignore for now
                pass

    return job

def checkFile(file):
    """return
        0: if file exists
        1: if file exists with zero size
       -1: if file does not exist or is not accessible"""

    if file is None or file=='': return -1

    try:
        size = os.stat(file)[ST_SIZE]
    except OSError:
        msg = '%s does not exist or is not accessible'%file
        return -1, msg

    if size == 0:
        msg = '%s has zero filesize'%file
        return 1, msg
    else:
        return 0, ''


def checkStatusFile(statusFilename):
    """ Reads status file and returns status accordingly
        0 = PASSED, 1 = FAILED, other = FAILED
        Return None if can't be accessed.
    """

    p,statname = os.path.split(statusFilename)

    # statusFilename does not exist or exists with zero size
    # ccode= 0: if file exists
    # ccode= 1: if file exists with zero size
    # ccode=-1: if file does not exist or is not accessible
    ccode,errmsg = checkFile(statusFilename)

    # statusFilename exists and has a value
    # --------------------------------------
    if ccode == 0:
        fp = open(statusFilename)
        stat = int(fp.read())
        fp.close()
        if stat == 0:
            # PASS
            newStatus = atsut.PASSED
        elif stat == 1:
            # FAIL
            newStatus = atsut.FAILED
        else:
            # stat not in [0,1]
            m = '%s has value != 0 (PASS) or 1 (FAIL)'%statname
            #print 'ERROR: %s: stat=%d'%(m,stat)
            #if debug: printObjInfo(self,msg=m)
            newStatus = atsut.FAILED
    else:
        newStatus = None

    return newStatus
