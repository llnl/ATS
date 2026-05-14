from collections import defaultdict
import types
import unittest

from ats.atsut import CREATED, PASSED, RUNNING
from ats.ready_queue import ReadyWorkSet


class ReadyScheduler:
    """Minimal scheduler matching the docs/source/scheduler_extensions.rst example."""

    def __init__(self):
        self.tests_by_serial = {}
        self.order = {}
        self.remaining_waits = {}
        self.tests_by_block = defaultdict(list)
        self.blocks = {}
        self.ready = ReadyWorkSet(
            item_lookup=self.tests_by_serial.get,
            order_lookup=lambda test: self.order[test.serialNumber],
        )

    def add_tests(self, tests):
        tests = list(tests)
        next_order = len(self.order)
        for offset, test in enumerate(tests):
            self.tests_by_serial[test.serialNumber] = test
            self.order[test.serialNumber] = next_order + offset
            self.remaining_waits[test.serialNumber] = sum(
                1 for parent in test.waitUntil
                if parent.status in (CREATED, RUNNING)
            )
            if getattr(test, "block", None):
                self.tests_by_block[test.block].append(test)

        for test in tests:
            self.ready.enqueue_if_ready(test, self.is_ready)

    def is_ready(self, test):
        if test is None:
            return False
        if test.status is not CREATED:
            return False
        if self.remaining_waits.get(test.serialNumber, 0) != 0:
            return False
        if any(parent.status in (CREATED, RUNNING) for parent in test.waitUntil):
            return False
        return not self.is_blocked(test)

    def is_blocked(self, test):
        block = getattr(test, "block", None)
        if not block:
            return False
        owner = self.blocks.get(block)
        return owner is not None and owner != test.group.number

    def add_block(self, test):
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
        block = getattr(test, "block", None)
        self.remove_block(test)

        for dependent in getattr(test, "dependents", []):
            if test not in getattr(dependent, "waitUntil", []):
                continue
            serial = dependent.serialNumber
            remaining = self.remaining_waits.get(serial, 0)
            if remaining > 0:
                self.remaining_waits[serial] = remaining - 1
            self.ready.enqueue_if_ready(dependent, self.is_ready)

        if block and block not in self.blocks:
            for candidate in self.tests_by_block.get(block, []):
                self.ready.enqueue_if_ready(candidate, self.is_ready)

    def next_ready(self, machine):
        test, _blocked = self.ready.pop_next(
            machine.remainingCapacity(),
            self.is_ready,
            machine.canRunNow,
        )
        return test

    def start_available(self, machine):
        while True:
            test = self.next_ready(machine)
            if test is None:
                return
            self.add_block(test)
            if not machine.startRun(test):
                self.remove_block(test)
                self.ready.enqueue_if_ready(test, self.is_ready)
                return


class _Group(list):
    def __init__(self, number, tests=()):
        super().__init__(tests)
        self.number = number
        self.isBlocking = False


class _Machine:
    def __init__(self, capacity, blocked_serials=None):
        self.capacity = capacity
        self.blocked_serials = set(blocked_serials or [])
        self.launched = []

    def remainingCapacity(self):
        return self.capacity

    def canRunNow(self, test):
        return test.serialNumber not in self.blocked_serials and test.np <= self.capacity

    def startRun(self, test):
        if not self.canRunNow(test):
            return False
        self.launched.append(test.serialNumber)
        self.capacity -= test.np
        test.status = RUNNING
        return True


def _make_test(serial, np=1, block=None, wait_until=None, priority=None):
    return types.SimpleNamespace(
        serialNumber=serial,
        status=CREATED,
        waitUntil=list(wait_until or []),
        dependents=[],
        block=block,
        independent=False,
        np=np,
        priority=priority if priority is not None else np,
    )


class ReadySchedulerExampleTest(unittest.TestCase):
    def test_launches_ready_work_and_unblocks_direct_dependents(self):
        parent = _make_test(1, np=1, block="case")
        child = _make_test(2, np=1, block="case", wait_until=[parent])
        other = _make_test(3, np=1, block="other")
        parent.dependents = [child]

        group = _Group(1, [parent, child])
        other_group = _Group(2, [other])
        parent.group = group
        child.group = group
        other.group = other_group

        scheduler = ReadyScheduler()
        scheduler.add_tests([parent, child, other])

        machine = _Machine(capacity=1)
        scheduler.start_available(machine)
        self.assertEqual(machine.launched, [1])
        self.assertIs(parent.status, RUNNING)
        self.assertIs(child.status, CREATED)

        parent.status = PASSED
        machine.capacity = 1
        scheduler.test_ended(parent)
        scheduler.start_available(machine)

        self.assertEqual(machine.launched, [1, 2])
        self.assertIs(child.status, RUNNING)

    def test_prefers_default_processor_count_priority_and_restores_blocked_candidate(self):
        small = _make_test(1, np=1, block="small")
        large = _make_test(2, np=4, block="large")
        small.group = _Group(1, [small])
        large.group = _Group(2, [large])

        scheduler = ReadyScheduler()
        scheduler.add_tests([small, large])

        machine = _Machine(capacity=4, blocked_serials={2})
        scheduler.start_available(machine)
        self.assertEqual(machine.launched, [1])
        self.assertIs(small.status, RUNNING)
        self.assertIs(large.status, CREATED)

        small.status = PASSED
        machine.capacity = 4
        machine.blocked_serials.clear()
        scheduler.test_ended(small)
        scheduler.start_available(machine)

        self.assertEqual(machine.launched, [1, 2])
        self.assertIs(large.status, RUNNING)

    def test_default_priority_uses_item_priority(self):
        low_priority_large = _make_test(1, np=4, priority=10)
        high_priority_small = _make_test(2, np=1, priority=20)
        tests_by_serial = {
            low_priority_large.serialNumber: low_priority_large,
            high_priority_small.serialNumber: high_priority_small,
        }
        order = {
            low_priority_large.serialNumber: 0,
            high_priority_small.serialNumber: 1,
        }
        ready = ReadyWorkSet(
            item_lookup=tests_by_serial.get,
            order_lookup=lambda test: order[test.serialNumber],
        )
        ready.enqueue_if_ready(low_priority_large, lambda test: test.status is CREATED)
        ready.enqueue_if_ready(high_priority_small, lambda test: test.status is CREATED)

        selected, blocked = ready.pop_next(
            available_slots=4,
            ready_predicate=lambda test: test.status is CREATED,
            can_run=lambda _test: True,
        )

        self.assertIs(selected, high_priority_small)
        self.assertFalse(blocked)


if __name__ == "__main__":
    unittest.main()
