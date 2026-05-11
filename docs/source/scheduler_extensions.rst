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

``ats.ready_queue.ReadyWorkSet`` stores work that is structurally ready but
still needs a machine capacity check.  It groups work into resource buckets,
usually processor counts, and returns the largest fitting candidate first.

The class is intentionally policy-light.  The owner supplies:

* ``item_lookup(serial)`` to map stable ids back to live test objects;
* ``order_lookup(item)`` to preserve scheduler order inside buckets;
* an optional ``resource_bucket(item)`` if ``item.np`` is not the right bucket;
* a ``ready_predicate(item)`` each time candidates are enqueued or popped;
* a ``can_run(item)`` predicate, normally ``machine.canRunNow``.

``ReadyWorkSet`` does not decide what "ready" means.  A scheduler commonly
defines readiness as: created, dependencies complete, not directory-blocked,
and still relevant to the current run.

Beginning Tutorial: A Cached Ready Scheduler
============================================

A scheduler can use ``ReadyWorkSet`` to avoid rescanning every created test on
every pass.

::

   from ats.atsut import CREATED, RUNNING
   from ats.ready_queue import ReadyWorkSet

   class ReadyScheduler:
       def __init__(self):
           self.tests_by_serial = {}
           self.order = {}
           self.ready = ReadyWorkSet(
               item_lookup=self.tests_by_serial.get,
               order_lookup=lambda test: self.order[test.serialNumber],
           )

       def add_tests(self, tests):
           for test in tests:
               self.tests_by_serial[test.serialNumber] = test
               self.order[test.serialNumber] = len(self.order)
               self.ready.enqueue_if_ready(test, self.is_ready)

       def is_ready(self, test):
           if test.status is not CREATED:
               return False
           return not any(parent.status in (CREATED, RUNNING)
                          for parent in test.waitUntil)

       def start_available(self, machine):
           available = machine.remainingCapacity()
           while True:
               test, blocked = self.ready.pop_next(
                   available,
                   self.is_ready,
                   machine.canRunNow,
               )
               if test is None:
                   return
               machine.startRun(test)
               available = machine.remainingCapacity()

Real schedulers also need to update dependent tests when a parent completes and
to handle directory blocks, retries, and logging.  The example shows the
division of labor: the ready set stores candidates; the scheduler owns
dependency policy; the machine owns resource admission.

Design Checklist
================

When adding a scheduler extension:

* keep application-specific state outside ATS;
* call machine resource checks before launch;
* preserve ordering only where required by correctness;
* test completion bursts, dependency chains, and retry/reset behavior.
