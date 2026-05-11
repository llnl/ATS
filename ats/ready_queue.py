"""Cached ready-queue helpers for ATS schedulers.

``ReadyWorkSet`` tracks work that is structurally ready but still needs a
machine-specific capacity check before launch.  It keeps FIFO scheduler order
within resource buckets, prefers the largest bucket that fits the current
capacity, and restores deferred candidates when a machine policy cannot run
them yet.

Items are usually ``ats.tests.AtsTest`` instances, but the class only requires
test-like objects with stable serial identifiers.  By default, an item must
have:

* ``serialNumber``: integer-like unique id for this scheduler;
* ``np``: optional integer-like processor count used as the resource bucket.

Schedulers supply callbacks for lookup, ordering, readiness, and machine
admission.  ``ReadyWorkSet`` deliberately does not know what CREATED, waits,
directory blocks, retries, or machine resources mean.
"""
from collections import defaultdict
import heapq


class ReadyWorkSet:
    """Maintain resource-binned heaps of structurally ready scheduler work.

    The work set stores heap entries as ``(order, serial)`` tuples rather than
    storing item objects directly.  This keeps heap ordering stable and lets a
    scheduler's readiness predicate see the current live object each time a
    candidate is considered.
    """

    def __init__(self, item_lookup, order_lookup, resource_bucket=None, serial_lookup=None):
        """Create an empty ready work set.

        Args:
            item_lookup (callable): Function with signature
                ``item_lookup(serial: int) -> object | None``.  It maps a
                serial id from a heap entry back to the live scheduler item.
            order_lookup (callable): Function with signature
                ``order_lookup(item: object) -> int``.  Lower values run first
                inside one resource bucket.
            resource_bucket (callable, optional): Function with signature
                ``resource_bucket(item: object) -> int``.  It maps an item to a
                positive resource bucket.  The default uses ``item.np`` or
                ``1`` when ``np`` is missing.
            serial_lookup (callable, optional): Function with signature
                ``serial_lookup(item: object) -> int``.  It returns the stable
                unique id for an item.  The default uses ``item.serialNumber``.
        """
        self._item_lookup = item_lookup
        self._order_lookup = order_lookup
        self._resource_bucket = resource_bucket or self.default_resource_bucket
        self._serial_lookup = serial_lookup or self.default_serial
        self.reset()

    def reset(self):
        """Clear all ready buckets and membership tracking.

        Returns:
            None.
        """
        self._ready_heaps = defaultdict(list)
        self._ready_serials = set()

    @staticmethod
    def default_resource_bucket(item):
        """Map an ATS test-like item to its processor-count bucket.

        Args:
            item (object): Test-like object.  If present, ``item.np`` must be
                integer-like.

        Returns:
            int: ``max(1, int(item.np))``, or ``1`` if ``item`` has no ``np``.
        """
        return max(1, int(getattr(item, "np", 1)))

    @staticmethod
    def default_serial(item):
        """Return an ATS test-like item's stable serial identifier.

        Args:
            item (object): Test-like object with integer-like
                ``item.serialNumber``.

        Returns:
            int: The item's stable serial identifier.
        """
        return item.serialNumber

    def bucket_for(self, item):
        """Map ``item`` to a positive integer resource bucket.

        Args:
            item (object): Scheduler item accepted by this work set's
                ``resource_bucket`` callback.

        Returns:
            int: Positive resource bucket for ``item``.
        """
        return max(1, int(self._resource_bucket(item)))

    def order_of(self, item):
        """Return the stable scheduler order used inside ready buckets.

        Args:
            item (object): Scheduler item accepted by this work set's
                ``order_lookup`` callback.

        Returns:
            int: Stable order key.  Lower values are selected first inside the
            same resource bucket.
        """
        return self._order_lookup(item)

    def enqueue_if_ready(self, item, ready_predicate):
        """Add ``item`` to the ready set if the supplied predicate accepts it.

        Args:
            item (object | None): Scheduler item to enqueue.  ``None`` is
                ignored.
            ready_predicate (callable): Function with signature
                ``ready_predicate(item: object) -> bool``.  It should return
                ``True`` only when the item is structurally ready for scheduler
                consideration.

        Returns:
            bool: ``True`` if a new heap entry was added, otherwise ``False``.
                Duplicate serial ids are ignored.
        """
        if item is None or not ready_predicate(item):
            return False
        serial = self._serial_lookup(item)
        if serial in self._ready_serials:
            return False
        heapq.heappush(self._ready_heaps[self.bucket_for(item)], self._heap_key(item))
        self._ready_serials.add(serial)
        return True

    def pop_next(self, available_slots, ready_predicate, can_run, blocked_predicate=None):
        """Pop the largest fitting runnable item while restoring deferred candidates.

        Args:
            available_slots (int): Current machine capacity.  Buckets larger
                than this value are skipped.
            ready_predicate (callable): Function with signature
                ``ready_predicate(item: object) -> bool``.  It is rechecked for
                each candidate so stale heap entries can be discarded.
            can_run (callable): Function with signature
                ``can_run(item: object) -> bool``.  This is normally
                ``machine.canRunNow`` and is the final machine-admission check.
            blocked_predicate (callable, optional): Function with signature
                ``blocked_predicate(item: object) -> bool``.  When it returns
                ``True``, the candidate is left queued and the returned blocked
                flag is set.  This is for scheduler-owned temporary blockers
                that are not represented by ``ready_predicate``.

        Returns:
            tuple: ``(item, blocked)`` where ``item`` is the selected scheduler
            item or ``None``.  ``blocked`` is ``True`` if at least one otherwise
            ready candidate was retained by ``blocked_predicate``.

        Notes:
            Candidates that still satisfy ``ready_predicate`` but fail
            ``can_run`` are restored to their original buckets before return.
            Candidates that no longer satisfy ``ready_predicate`` are discarded
            as stale entries.
        """
        persistence_blocked = False
        deferred = defaultdict(list)
        for bucket in sorted(self._ready_heaps.keys(), reverse=True):
            if bucket > available_slots:
                continue
            heap = self._ready_heaps[bucket]
            while heap:
                order_index, serial = heapq.heappop(heap)
                self._ready_serials.discard(serial)
                candidate = self._item_lookup(serial)
                if candidate is None or not ready_predicate(candidate):
                    continue
                if blocked_predicate is not None and blocked_predicate(candidate):
                    persistence_blocked = True
                    deferred[bucket].append((order_index, serial))
                    continue
                if can_run(candidate):
                    self._restore_deferred(deferred)
                    return candidate, persistence_blocked
                deferred[bucket].append((order_index, serial))

        self._restore_deferred(deferred)
        return None, persistence_blocked

    def remove(self, item):
        """Remove ``item`` from its ready bucket if it is still queued.

        Args:
            item (object | None): Scheduler item to remove.  ``None`` is
                ignored.

        Returns:
            bool: ``True`` if the exact heap entry was found and removed,
            otherwise ``False``.
        """
        if item is None:
            return False
        serial = self._serial_lookup(item)
        bucket = self.bucket_for(item)
        heap = self._ready_heaps.get(bucket)
        if not heap:
            self._ready_serials.discard(serial)
            return False
        key = self._heap_key(item)
        try:
            heap.remove(key)
        except ValueError:
            self._ready_serials.discard(serial)
            return False
        heapq.heapify(heap)
        self._ready_serials.discard(serial)
        return True

    def has_candidates(self):
        """Return whether any ready bucket still contains heap entries.

        Returns:
            bool: ``True`` if any bucket contains queued heap entries.  This is
            a cheap structural check; entries may still be stale.
        """
        return any(heap for heap in self._ready_heaps.values())

    def ready_count(self, ready_predicate):
        """Count currently queued items that still satisfy ``ready_predicate``.

        Args:
            ready_predicate (callable): Function with signature
                ``ready_predicate(item: object) -> bool``.

        Returns:
            int: Number of queued serial ids whose live item exists and still
            satisfies ``ready_predicate``.
        """
        count = 0
        for serial in self._ready_serials:
            candidate = self._item_lookup(serial)
            if candidate is not None and ready_predicate(candidate):
                count += 1
        return count

    def live_ready_count(self):
        """Return the cached ready-set size.

        Returns:
            int: Number of serial ids currently tracked as queued.  This is
            cheap and may include stale entries that will be discarded by a
            later ``pop_next`` or ``ready_count`` call.
        """
        return len(self._ready_serials)

    def bucket_counts(self, predicate=None):
        """Return queued item counts by resource bucket.

        Args:
            predicate (callable, optional): Function with signature
                ``predicate(item: object) -> bool``.  If provided, only live
                items accepted by this predicate are counted.

        Returns:
            dict: Mapping ``bucket: int`` to ``count: int`` for queued live
            items.
        """
        counts = defaultdict(int)
        for serial in self._ready_serials:
            item = self._item_lookup(serial)
            if item is None:
                continue
            if predicate is not None and not predicate(item):
                continue
            counts[self.bucket_for(item)] += 1
        return dict(counts)

    def buckets(self):
        """Return a snapshot of bucket keys currently known to the work set.

        Returns:
            list: Resource bucket integers.  Empty buckets may be present if
            they previously held work.
        """
        return list(self._ready_heaps.keys())

    def candidates_for_bucket(self, bucket, ready_predicate, candidate_predicate=None, limit=None):
        """Return queued candidates from one bucket without mutating the work set.

        Args:
            bucket (int): Resource bucket to inspect.
            ready_predicate (callable): Function with signature
                ``ready_predicate(item: object) -> bool``.  Stale or no-longer
                ready candidates are skipped in the returned list, but not
                removed from the heap.
            candidate_predicate (callable, optional): Additional filter with
                signature ``candidate_predicate(item: object) -> bool``.
            limit (int, optional): Maximum number of candidates to return.  If
                ``None``, all matching candidates in the bucket are returned.

        Returns:
            list: Live scheduler items from ``bucket`` in stable in-bucket
            order.
        """
        candidates = []
        for _order_index, serial in sorted(self._ready_heaps.get(bucket, [])):
            candidate = self._item_lookup(serial)
            if candidate is None or not ready_predicate(candidate):
                continue
            if candidate_predicate is not None and not candidate_predicate(candidate):
                continue
            candidates.append(candidate)
            if limit is not None and len(candidates) >= limit:
                break
        return candidates

    def _heap_key(self, item):
        """Build the stored heap key for ``item``.

        Args:
            item (object): Scheduler item accepted by ``order_lookup`` and
                ``serial_lookup``.

        Returns:
            tuple: ``(order: int, serial: int)``.
        """
        return (self._order_lookup(item), self._serial_lookup(item))

    def _restore_deferred(self, deferred):
        """Restore deferred heap entries after a pop attempt.

        Args:
            deferred (dict): Mapping ``bucket: int`` to lists of heap-key
                tuples ``(order: int, serial: int)``.

        Returns:
            None.
        """
        for bucket, items in deferred.items():
            for item in items:
                heapq.heappush(self._ready_heaps[bucket], item)
                self._ready_serials.add(item[-1])
