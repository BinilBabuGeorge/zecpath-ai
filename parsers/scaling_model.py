"""
Scaling model (Day 60)

Two things the scalability strategy needs and a single laptop cannot measure directly:

  1. CAPACITY ARITHMETIC. How many workers does a given volume need, if one request of each kind costs what the benchmark measured?
  2. A LOAD-BALANCING SIMULATOR. What does each way of spreading requests over workers do to the latency of the quick requests when
     slow ones share the same workers?

WHAT THIS IS NOT. It is a model, not a measurement. Service times are inputs (the benchmark's measured medians, with a spread added);
arrivals are random (Poisson); a worker serves one request at a time, first come first served; there is no network, no start-up, no
failure. It answers "which design is better, and by how much, under these assumptions", and it is checked against queueing theory
(an M/M/1 queue simulated here must match the textbook mean wait) so the simulator itself is trustworthy. It does not predict what a
production cluster will do.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


# ======================================================================================================================
# 1. Capacity arithmetic
# ======================================================================================================================
def utilization(arrival_per_s: float, service_s: float, workers: int) -> float:
    """Fraction of the workers' time that is busy. Above 1.0 the queue grows without limit."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    return arrival_per_s * service_s / workers


def workers_needed(arrival_per_s: float, service_s: float, target_utilization: float = 0.6) -> int:
    """Smallest worker count that keeps utilization at or below the target. 0.6 leaves room for bursts: queueing delay grows
    steeply as utilization approaches 1, so a pool is sized well below full."""
    if not 0 < target_utilization < 1:
        raise ValueError("target_utilization must be between 0 and 1")
    if arrival_per_s < 0 or service_s < 0:
        raise ValueError("rates and times cannot be negative")
    return max(1, math.ceil(arrival_per_s * service_s / target_utilization))


def erlang_c(workers: int, offered_load: float) -> float:
    """Probability that an arriving request has to wait, in an M/M/c queue (offered_load = arrival rate x service time)."""
    if offered_load >= workers:
        return 1.0
    summation = sum(offered_load ** k / math.factorial(k) for k in range(workers))
    top = offered_load ** workers / math.factorial(workers) * workers / (workers - offered_load)
    return top / (summation + top)


def mean_wait_mmc(arrival_per_s: float, service_s: float, workers: int) -> float:
    """Textbook mean time a request waits in queue (not counting its own service), M/M/c. Infinity if overloaded."""
    load = arrival_per_s * service_s
    if load >= workers:
        return math.inf
    return erlang_c(workers, load) * service_s / (workers - load)


@dataclass(frozen=True)
class CapacityRow:
    scenario: str
    applications_per_day: int
    peak_per_s: float
    cpu_seconds_per_application: float
    cores_at_target: int
    workers_with_spare: int
    utilization_at_workers: float


def capacity_plan(applications_per_day: int, cpu_s_per_application: float, peak_share_in_busiest_hour: float = 0.15,
                  target_utilization: float = 0.6, spare_workers: int = 1, name: str = "") -> CapacityRow:
    """Workers for the BUSIEST HOUR, plus spare workers so losing one is not an outage."""
    peak = applications_per_day * peak_share_in_busiest_hour / 3600.0
    needed = workers_needed(peak, cpu_s_per_application, target_utilization)
    total = needed + spare_workers
    return CapacityRow(name or f"{applications_per_day:,}/day", applications_per_day, round(peak, 4), cpu_s_per_application, needed, total,
                       round(utilization(peak, cpu_s_per_application, total), 4))


# ======================================================================================================================
# 2. Load-balancing simulator
# ======================================================================================================================
@dataclass(frozen=True)
class RequestClass:
    """A kind of request: how often it arrives and how long it takes (lognormal around the mean, `cv` = std/mean)."""
    name: str
    rate_per_s: float
    mean_service_s: float
    cv: float = 0.3


POLICIES = ("round_robin", "random", "least_connections", "shared_queue")


def _service_time(cls: RequestClass, rng: random.Random, exponential: bool = False) -> float:
    if exponential:
        return rng.expovariate(1.0 / cls.mean_service_s)
    if cls.cv <= 0:
        return cls.mean_service_s
    sigma2 = math.log(1 + cls.cv ** 2)
    mu = math.log(cls.mean_service_s) - sigma2 / 2
    return rng.lognormvariate(mu, math.sqrt(sigma2))


def generate_arrivals(classes: Sequence[RequestClass], horizon_s: float, seed: int, exponential: bool = False) -> List[Tuple[float, str, float]]:
    """(arrival time, class name, service time), sorted by arrival. Poisson arrivals per class, reproducible from the seed."""
    rng = random.Random(seed)
    events: List[Tuple[float, str, float]] = []
    for cls in classes:
        t = 0.0
        while cls.rate_per_s > 0:
            t += rng.expovariate(cls.rate_per_s)
            if t >= horizon_s:
                break
            events.append((t, cls.name, _service_time(cls, rng, exponential)))
    events.sort(key=lambda e: e[0])
    return events


def simulate(arrivals: Sequence[Tuple[float, str, float]], workers: int, policy: str, seed: int = 0) -> Dict[str, List[float]]:
    """Latency (wait + service) of every request, grouped by class. One FIFO server per worker; `shared_queue` is a single queue
    feeding whichever worker frees first (how a job queue behaves); the others choose a worker the moment the request arrives."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; choose from {POLICIES}")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    rng = random.Random(seed)
    free_at = [0.0] * workers
    unfinished: List[List[float]] = [[] for _ in range(workers)]      # finish times of requests still in each worker's queue
    latencies: Dict[str, List[float]] = {}
    rr = 0
    for arrival, cls, service in arrivals:
        if policy == "shared_queue":
            w = min(range(workers), key=lambda i: free_at[i])
        elif policy == "round_robin":
            w, rr = rr % workers, rr + 1
        elif policy == "random":
            w = rng.randrange(workers)
        else:                                                           # least_connections: fewest requests not yet finished
            for q in unfinished:
                q[:] = [f for f in q if f > arrival]
            w = min(range(workers), key=lambda i: (len(unfinished[i]), i))
        start = max(arrival, free_at[w])
        finish = start + service
        free_at[w] = finish
        unfinished[w].append(finish)
        latencies.setdefault(cls, []).append(finish - arrival)
    return latencies


def summarize_latencies(values: Sequence[float]) -> Dict[str, float]:
    s = sorted(values)
    if not s:
        return {"n": 0}
    pick = lambda q: s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]
    return {"n": len(s), "p50_ms": round(pick(0.5) * 1000, 2), "p95_ms": round(pick(0.95) * 1000, 2), "p99_ms": round(pick(0.99) * 1000, 2),
            "mean_ms": round(sum(s) / len(s) * 1000, 2), "max_ms": round(s[-1] * 1000, 2)}


def split_by_pool(arrivals: Sequence[Tuple[float, str, float]], fast: Sequence[str]) -> Tuple[list, list]:
    """Divide an arrival stream into the quick classes and everything else (to give each its own workers)."""
    quick = [a for a in arrivals if a[1] in fast]
    slow = [a for a in arrivals if a[1] not in fast]
    return quick, slow
