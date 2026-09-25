import types
import unittest

from ats.atsut import CREATED, PASSED
from ats.management import AtsManager
from ats.schedulers import StandardScheduler


class _Group(list):
    def __init__(self, number):
        """Create a sortable fake ATS group.

        Args:
            number (int): Stable group number used for scheduler ordering.
        """
        super().__init__()
        self.number = number
        self.totalPriority = 0

    def __lt__(self, other):
        """Compare fake groups by group number.

        Args:
            other (_Group): Group to compare against.

        Returns:
            bool: ``True`` when this group should sort before ``other``.
        """
        return self.number < other.number


class StreamingCoreHelperTest(unittest.TestCase):
    def test_streaming_definition_accepts_wrapped_group(self):
        """Verify streamed definitions normalize wrapper and list inputs."""
        manager = AtsManager()
        tests = [types.SimpleNamespace(serialNumber=1, group=object())]
        testcase = types.SimpleNamespace(atsGroup=tests)

        self.assertEqual(manager._streamingTestsFromDefinition(testcase), tests)
        self.assertEqual(manager._streamingTestsFromDefinition(tests), tests)
        self.assertEqual(manager._streamingTestsFromDefinition("not a test"), [])

    def test_streaming_finalize_waits_adds_missing_parent_once(self):
        """Verify streamed wait-finalization adds each live parent once."""
        manager = AtsManager()
        child = types.SimpleNamespace(serialNumber=2, waitUntil=[])
        parent = types.SimpleNamespace(
            serialNumber=1,
            status=CREATED,
            dependents=[child],
        )

        manager._streamingFinalizeWaits([child], [parent])
        manager._streamingFinalizeWaits([child], [parent])

        self.assertEqual(child.waitUntil, [parent])

        done_parent = types.SimpleNamespace(
            serialNumber=3,
            status=PASSED,
            dependents=[child],
        )
        manager._streamingFinalizeWaits([child], [done_parent])

        self.assertEqual(child.waitUntil, [parent])

    def test_streaming_distinct_names_match_ats_suffix_style(self):
        """Verify streamed duplicate names use the same suffixes as ATS collect."""
        manager = AtsManager()
        tests = [
            types.SimpleNamespace(name="sample"),
            types.SimpleNamespace(name="SAMPLE"),
            types.SimpleNamespace(name="sample"),
        ]

        manager._streamingEnsureDistinctNames(tests, {})

        self.assertEqual([test.name for test in tests], ["sample", "SAMPLE#2", "sample#3"])

    def test_standard_scheduler_accepts_incremental_interactive_tests(self):
        """Verify the default scheduler can load tests after initial load."""
        scheduler = StandardScheduler()
        scheduler.groups = []
        scheduled = []

        def record_schedule(*args):
            """Record one scheduler log message.

            Args:
                *args: Positional values passed by ``StandardScheduler``.

            Returns:
                None.
            """
            scheduled.append(args)

        scheduler.schedule = record_schedule
        group = _Group(7)
        test = types.SimpleNamespace(
            group=group,
            name="streamed",
            priority=3,
            serialNumber=11,
            totalPriority=5,
            waitUntil=[],
        )
        group.append(test)

        self.assertTrue(scheduler.addInteractiveTests([test]))

        self.assertEqual(scheduler.groups, [group])
        self.assertEqual(group.totalPriority, 5)
        self.assertEqual(len(scheduled), 1)


if __name__ == "__main__":
    unittest.main()
