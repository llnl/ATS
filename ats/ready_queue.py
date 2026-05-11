"""Cached ready-queue helpers for ATS schedulers.

``ReadyWorkSet`` tracks work that is structurally ready but still needs a
machine-specific capacity check before launch.  It keeps FIFO scheduler order
within resource buckets, prefers the largest bucket that fits the current
capacity, and restores deferred candidates when a machine policy cannot run
them yet.
"""
from collections import defaultdict
import heapq


class ReadyWorkSet:
    """Maintain resource-binned heaps of structurally ready scheduler work."""

    def __init__(self, item_lookup, order_lookup, resource_bucket=None, serial_lookup=None):
        self._item_lookup = item_lookup
        self._order_lookup = order_lookup
        self._resource_bucket = resource_bucket or self.default_resource_bucket
        self._serial_lookup = serial_lookup or self.default_serial
        self.reset()

    def reset(self):
        """Clear all ready buckets and membership tracking."""
        self._ready_heaps = defaultdict(list)
        self._ready_serials = set()

    @staticmethod
    def default_resource_bucket(item):
        """Map an ATS test-like item to its processor-count bucket."""
        return max(1, int(getattr(item, "np", 1)))

    @staticmethod
    def default_serial(item):
        """Return an ATS test-like item's stable serial identifier."""
        return item.serialNumber

    def bucket_for(self, item):
        """Map ``item`` to a positive integer resource bucket."""
        return max(1, int(self._resource_bucket(item)))

    def order_of(self, item):
        """Return the stable scheduler order used inside ready buckets."""
        return self._order_lookup(item)

    def enqueue_if_ready(self, item, ready_predicate):
        """Add ``item`` to the ready set if the supplied predicate accepts it."""
        if item is None or not ready_predicate(item):
            return False
        serial = self._serial_lookup(item)
        if serial in self._ready_serials:
            return False
        heapq.heappush(self._ready_heaps[self.bucket_for(item)], self._heap_key(item))
        self._ready_serials.add(serial)
        return True

    def pop_next(self, available_slots, ready_predicate, can_run, blocked_predicate=None):
        """Pop the largest fitting runnable item while restoring deferred candidates."""
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
        """Remove ``item`` from its ready bucket if it is still queued."""
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
        """Return whether any ready bucket still contains heap entries."""
        return any(heap for heap in self._ready_heaps.values())

    def ready_count(self, ready_predicate):
        """Count currently queued items that still satisfy ``ready_predicate``."""
        count = 0
        for serial in self._ready_serials:
            candidate = self._item_lookup(serial)
            if candidate is not None and ready_predicate(candidate):
                count += 1
        return count

    def live_ready_count(self):
        """Return the cached ready-set size."""
        return len(self._ready_serials)

    def bucket_counts(self, predicate=None):
        """Return queued item counts by resource bucket."""
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
        """Return a snapshot of bucket keys currently known to the work set."""
        return list(self._ready_heaps.keys())

    def candidates_for_bucket(self, bucket, ready_predicate, candidate_predicate=None, limit=None):
        """Return queued candidates from one bucket without mutating the work set."""
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
        return (self._order_lookup(item), self._serial_lookup(item))

    def _restore_deferred(self, deferred):
        for bucket, items in deferred.items():
            for item in items:
                heapq.heappush(self._ready_heaps[bucket], item)
                self._ready_serials.add(item[-1])
