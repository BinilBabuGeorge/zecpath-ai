"""
Performance helpers (Day 60)

BoundedLRU is the one cache used by every Day 60 optimization. It exists so that speed never costs unbounded memory or correctness:

  * BOUNDED   a hard limit on the number of entries (and optionally on total approximate bytes); the least recently used entry is
              evicted first, so a long-running worker's memory has a ceiling you can compute: max_items x the size of one entry.
  * SAFE      a lock around every operation, so threads sharing a cache cannot corrupt it.
  * EXACT     a cache only ever stores the result of a PURE function of its key (same key -> same result, no clock, no randomness),
              and callers get back values that cannot be changed behind the cache's back. A cache here can make a call faster; it
              can never make it different. tests/test_day60_performance.py compares optimized output with the pre-optimization output.
  * VISIBLE   hits, misses and evictions are counted, and every cache is registered by name so `all_cache_stats()` can report them
              (a cache nobody can inspect is a cache nobody can size).

Switching: set the environment variable ZECPATH_CACHE=off to disable every cache (each `get_or_compute` then just computes). That is the
fallback if a cache is ever suspected of hiding a bug, and the way the benchmark measures the uncached cost.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Hashable, Optional

_REGISTRY: Dict[str, "BoundedLRU"] = {}
_REGISTRY_LOCK = threading.Lock()


def caching_enabled() -> bool:
    return os.environ.get("ZECPATH_CACHE", "on").strip().lower() not in ("off", "0", "false", "no")


class BoundedLRU:
    def __init__(self, name: str, max_items: int, max_bytes: Optional[int] = None, sizeof: Optional[Callable[[Any], int]] = None) -> None:
        if max_items < 0:
            raise ValueError("max_items cannot be negative")
        self.name = name
        self.max_items = int(max_items)
        self.max_bytes = max_bytes
        self._sizeof = sizeof
        self._data: "OrderedDict[Hashable, Any]" = OrderedDict()
        self._sizes: Dict[Hashable, int] = {}
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        with _REGISTRY_LOCK:
            _REGISTRY[name] = self

    # -- core -----------------------------------------------------------------------------------------------------------
    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        """Return the cached value for `key`, computing and storing it on a miss. `compute` runs OUTSIDE the lock, so a slow
        computation never blocks other threads; two threads racing on one key may both compute it (harmless: the result is pure)."""
        if self.max_items == 0 or not caching_enabled():
            return compute()
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
        value = compute()
        self._store(key, value)
        return value

    def _store(self, key: Hashable, value: Any) -> None:
        size = self._sizeof(value) if self._sizeof else 0
        if self.max_bytes is not None and size > self.max_bytes:
            return                                              # one value bigger than the whole budget is never cached
        with self._lock:
            if key in self._data:
                self._bytes -= self._sizes.get(key, 0)
            self._data[key] = value
            self._data.move_to_end(key)
            self._sizes[key] = size
            self._bytes += size
            while len(self._data) > self.max_items or (self.max_bytes is not None and self._bytes > self.max_bytes):
                old, _ = self._data.popitem(last=False)
                self._bytes -= self._sizes.pop(old, 0)
                self.evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._sizes.clear()
            self._bytes = 0

    def reset_stats(self) -> None:
        with self._lock:
            self.hits = self.misses = self.evictions = 0

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {"name": self.name, "entries": len(self._data), "max_items": self.max_items, "approx_bytes": self._bytes,
                    "max_bytes": self.max_bytes, "hits": self.hits, "misses": self.misses, "evictions": self.evictions,
                    "hit_rate": round(self.hits / total, 4) if total else None}


def all_cache_stats() -> Dict[str, Dict[str, Any]]:
    with _REGISTRY_LOCK:
        caches = list(_REGISTRY.values())
    return {c.name: c.stats() for c in caches}


def clear_cache(name: str) -> None:
    with _REGISTRY_LOCK:
        cache = _REGISTRY.get(name)
    if cache is not None:
        cache.clear()


def clear_all_caches() -> None:
    with _REGISTRY_LOCK:
        caches = list(_REGISTRY.values())
    for c in caches:
        c.clear()
        c.reset_stats()


def percentile(sorted_samples, q: float) -> float:
    """Nearest-rank percentile of an ASCENDING list (q from 0 to 1)."""
    if not sorted_samples:
        raise ValueError("no samples")
    return sorted_samples[min(len(sorted_samples) - 1, max(0, int(q * (len(sorted_samples) - 1) + 0.5)))]


def compile_phrase_patterns(phrases, escape: bool = True):
    """[(phrase, compiled pattern)] for r"\\b<phrase>\\b", built ONCE.

    Several engines checked a list of phrases against every answer with re.search(rf"\\b{re.escape(p)}\\b", text) inside the loop, which
    rebuilds the pattern text and looks it up in the re cache for every phrase on every call (Day 60 profiling: a visible share of HR
    and screening scoring). The compiled pattern is the identical pattern, so matches are identical; only the rebuilding goes away.
    `escape=False` keeps the few call sites that deliberately passed plain words unescaped exactly as they were.
    """
    import re
    return [(p, re.compile(rf"\b{re.escape(p) if escape else p}\b")) for p in phrases]
