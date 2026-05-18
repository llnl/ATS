====================================
 Scheduler Extension Design Guide
====================================

This guide describes the reusable ATS ready-queue support used by larger or
more specialized schedulers.  The examples are intentionally domain-neutral.
Application drivers can use these APIs to add scheduling policy without
teaching ATS about application-specific status files, reports, or test
metadata.

Core Responsibilities
=====================

ATS owns the generic execution model:

* tests are collected into ATS ``AtsTest`` objects;
* dependencies are represented with ``waitUntil`` and ``dependents``;
* the active scheduler decides which created tests should be offered to the
  machine;
* the machine owns launch, running-test tracking, completion detection, and
  final test-end notification.

Application drivers own policy:

* what "structurally ready" means for their tests;
* how tests should be bucketed for resource-aware scheduling;
* how retry and group-output behavior interacts with cached readiness.

That split keeps ATS reusable.  A driver can use ATS queues while keeping
domain-specific data structures outside the ATS package.

Scheduler Flow
==============

The normal interactive flow is:

1. ``manager.collectTests()`` executes input files and defines tests.
2. The scheduler prioritizes and loads the collected interactive tests.
3. ``scheduler.step()`` starts runnable tests while the machine has capacity.
4. ``machine.checkRunning()`` detects completed tests.
5. ``machine.testEnded(test, status)`` records final machine-level state.
6. The scheduler is notified and can unblock dependent work.

A custom scheduler should preserve two invariants:

* scheduler operations and machine operations run on the main ATS thread unless
  the driver has explicitly built a safe handoff;
* resource policy remains authoritative in the machine.  A scheduler may cache
  readiness, but it should still call ``machine.canRunNow(test)`` or
  ``machine.startRun(test)`` before consuming resources.

ReadyWorkSet
============

``ats.ready_queue.ReadyWorkSet`` stores work that is structurally ready.  It
groups work into scheduler-defined priority buckets and returns the highest-priority
runnable candidate first.

The class is intentionally policy-light.  The owner supplies:

* ``item_lookup(serial)`` to map stable ids back to live test objects;
* ``order_lookup(item)`` to preserve scheduler order inside buckets;
* ``priority_lookup(item)`` to define the priority of a test.
* a ``ready_predicate(item)`` each time candidates are enqueued or popped;
* a ``can_run(item)`` predicate, normally ``machine.canRunNow``.

``ReadyWorkSet`` does not decide what "ready" means.  A scheduler commonly
defines readiness as: created, dependencies complete, not directory-blocked,
and still relevant to the current run.

Directory Blocks
================

The user-facing directory-blocking model is documented in
:ref:`directory blocking <directory_blocking>`.  Scheduler extensions only need
to preserve the scheduler responsibilities that follow from that model.

Schedulers that cache readiness need to handle block changes incrementally:

* index tests by ``test.block`` when tests are loaded;
* reject candidates whose block is currently owned by another group;
* after a test ends, remove its group's block if the group is no longer active;
* when a block clears, reconsider only tests indexed under that block.

Beginning Tutorial: A Cached Ready Scheduler
============================================

A scheduler can use ``ReadyWorkSet`` to avoid rescanning every created test on
every pass.  This example is intentionally small, but it includes the parts
needed for a copied scheduler to stay correct: initial indexing, direct
dependent updates, directory-block updates, and launch-failure recovery.

::

   from collections import defaultdict

   from ats.atsut import CREATED, RUNNING
   from ats.ready_queue import ReadyWorkSet

   class ReadyScheduler:
       def __init__(self):
           # ``ReadyWorkSet`` stores only compact heap entries, so the
           # scheduler must provide a way to map a serial number back to the
           # live ATS test object.
           self.tests_by_serial = {}

           # Stable order is separate from serial number.  Serial numbers are
           # usually creation order, but a scheduler may sort groups or apply
           # priority before loading tests.  Keep the order you want preserved
           # inside each priority bucket.
           self.order = {}

           # Cache the number of unfinished wait dependencies for each test.
           # This turns "did this parent unblock anything?" into updates of the
           # completed test's direct dependents instead of a full-suite scan.
           self.remaining_waits = {}

           # ATS directory blocks prevent two non-independent groups from
           # running in the same directory.  When a block clears, only tests in
           # that directory need to be reconsidered.
           self.tests_by_block = defaultdict(list)
           self.blocks = {}

           # The ready set decides queue mechanics: priority buckets, stable
           # in-bucket ordering, stale-entry cleanup, and temporary deferral of
           # candidates that are ready but cannot pass machine policy yet.
           self.ready = ReadyWorkSet(
               item_lookup=self.tests_by_serial.get,
               order_lookup=lambda test: self.order[test.serialNumber],
           )

       def add_tests(self, tests):
           # Load tests in the scheduler order you want to preserve.  A real
           # scheduler usually calls this after ATS has built and sorted groups.
           tests = list(tests)
           next_order = len(self.order)
           for offset, test in enumerate(tests):
               self.tests_by_serial[test.serialNumber] = test
               self.order[test.serialNumber] = next_order + offset

               # Count only unfinished parents.  Completed parents should not
               # keep a test out of the initial ready set.
               self.remaining_waits[test.serialNumber] = sum(
                   1 for parent in test.waitUntil
                   if parent.status in (CREATED, RUNNING)
               )

               # Record block membership once so clearing a directory block can
               # revisit only affected tests.
               if getattr(test, "block", None):
                   self.tests_by_block[test.block].append(test)

           for test in tests:
               # ``enqueue_if_ready`` calls back into scheduler policy.  The
               # ready set never decides what CREATED, waits, or blocks mean.
               self.ready.enqueue_if_ready(test, self.is_ready)

       def is_ready(self, test):
           # "Ready" here means structurally ready for scheduler consideration.
           # It does not mean resources are currently available; the machine
           # still decides that later through ``canRunNow`` / ``startRun``.
           if test is None:
               return False
           if test.status is not CREATED:
               return False
           if self.remaining_waits.get(test.serialNumber, 0) != 0:
               return False

           # The cached counter is the fast path.  This direct check is a
           # defensive guard for schedulers that can mutate waitUntil after
           # initial indexing or after retry/reset handling.
           if any(parent.status in (CREATED, RUNNING)
                  for parent in test.waitUntil):
               return False
           return not self.is_blocked(test)

       def is_blocked(self, test):
           # Directory blocks are owned by the group that is currently running
           # in that directory.  Tests from that same group may continue; tests
           # from other groups must wait.
           block = getattr(test, "block", None)
           if not block:
               return False
           owner = self.blocks.get(block)
           return owner is not None and owner != test.group.number

       def add_block(self, test):
           # Match ATS's default block policy: if any non-independent member of
           # a group has a block directory, the whole group owns that block
           # while one of its blocking members is CREATED or RUNNING.
           group = test.group
           if getattr(group, "isBlocking", False):
               return
           for member in group:
               if getattr(member, "independent", False):
                   continue
               block = getattr(member, "block", None)
               if block:
                   group.isBlocking = True
                   self.blocks[block] = group.number

       def remove_block(self, test):
           # A group keeps its directory block until all non-independent group
           # members have left CREATED/RUNNING.  When that happens, sibling
           # tests from other groups in the same directory may become ready.
           group = test.group
           if not getattr(group, "isBlocking", False):
               return
           for member in group:
               if getattr(member, "independent", False):
                   continue
               if member.status in (CREATED, RUNNING):
                   return
           group.isBlocking = False
           for member in group:
               if getattr(member, "independent", False):
                   continue
               block = getattr(member, "block", None)
               if block:
                   self.blocks.pop(block, None)

       def test_ended(self, test):
           # Completion can create new ready work in two local ways:
           # 1. direct dependents may have one fewer unfinished parent;
           # 2. the completed test's directory block may have cleared.
           block = getattr(test, "block", None)
           self.remove_block(test)

           for dependent in getattr(test, "dependents", []):
               # Some ATS bookkeeping can list broad dependents.  Only update
               # tests that were actually waiting on this completed parent.
               if test not in getattr(dependent, "waitUntil", []):
                   continue
               serial = dependent.serialNumber
               remaining = self.remaining_waits.get(serial, 0)
               if remaining > 0:
                   self.remaining_waits[serial] = remaining - 1

               # This is cheap even if the dependent is not ready yet.  The
               # scheduler predicate filters out tests with other unfinished
               # parents or active blocks.
               self.ready.enqueue_if_ready(dependent, self.is_ready)

           if block and block not in self.blocks:
               # Avoid rescanning all CREATED tests just because one directory
               # block cleared.  Only tests from that block can be affected.
               for candidate in self.tests_by_block.get(block, []):
                   self.ready.enqueue_if_ready(candidate, self.is_ready)

       def next_ready(self, machine):
           # ``pop_next`` picks the highest-priority bucket, then checks
           # machine policy.  Candidates that are still structurally ready but
           # cannot run now are restored so a later scheduler pass can
           # reconsider them.
           test, _blocked = self.ready.pop_next(
               self.is_ready,
               machine.canRunNow,
           )
           return test

       def start_available(self, machine):
           # Keep launching until the ready set has no machine-runnable work or
           # the machine is full.  Real schedulers usually also log each launch.
           while True:
               test = self.next_ready(machine)
               if test is None:
                   return
               self.add_block(test)
               if not machine.startRun(test):
                   # If the machine refuses a launch after selection, undo the
                   # scheduler-side block and requeue the test if it is still
                   # structurally ready.
                   self.remove_block(test)
                   self.ready.enqueue_if_ready(test, self.is_ready)
                   return

Production schedulers also need logging, retry behavior, group-output handling,
periodic reports, and a cheap "work remains" check.  The example shows the
division of labor: the ready set stores candidates; the scheduler owns
dependency and block policy; the machine owns resource admission.

Design Checklist
================

When adding a scheduler extension:

* keep application-specific state outside ATS;
* call machine resource checks before launch;
* preserve ordering only where required by correctness;
* test completion bursts, dependency chains, and retry/reset behavior.
