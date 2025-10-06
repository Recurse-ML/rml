"""Simple timing utilities for RML client."""

import time
from contextlib import contextmanager
from typing import Dict, List


class TimingCollector:
    """Collects timing data for client operations."""

    def __init__(self):
        self.timings: Dict[str, List[float]] = {}
        self.start_time = time.time()

    def record(self, operation: str, duration: float):
        """Record a timing measurement."""
        if operation not in self.timings:
            self.timings[operation] = []
        self.timings[operation].append(duration)

    @contextmanager
    def time_operation(self, operation: str):
        """Context manager to time an operation."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.record(operation, duration)

    def get_total_time(self) -> float:
        """Get total elapsed time."""
        return time.time() - self.start_time

    def get_summary(self) -> Dict[str, any]:
        """Get timing summary."""
        total = self.get_total_time()
        summary = {"total_time": total, "operations": {}}

        for operation, durations in self.timings.items():
            total_duration = sum(durations)
            summary["operations"][operation] = {
                "total": total_duration,
                "count": len(durations),
                "avg": total_duration / len(durations),
                "percentage": (total_duration / total) * 100 if total > 0 else 0,
            }

        return summary

    def format_report(self) -> str:
        """Format timing data as a human-readable report."""
        summary = self.get_summary()
        lines = []

        lines.append("\n" + "=" * 80)
        lines.append("CLIENT-SIDE LATENCY REPORT")
        lines.append("=" * 80)
        lines.append(f"Total Time: {summary['total_time']:.3f}s\n")

        # Sort operations by total time (descending)
        sorted_ops = sorted(
            summary["operations"].items(), key=lambda x: x[1]["total"], reverse=True
        )

        lines.append("Operation Breakdown:")
        lines.append("-" * 80)
        for operation, stats in sorted_ops:
            lines.append(
                f"  {operation:40s} {stats['total']:8.3f}s ({stats['percentage']:5.1f}%) "
                f"[count={stats['count']}, avg={stats['avg']:.3f}s]"
            )

        lines.append("=" * 80 + "\n")
        return "\n".join(lines)


# Global timing collector
_timing_collector: TimingCollector | None = None


def init_timing():
    """Initialize timing collection."""
    global _timing_collector
    _timing_collector = TimingCollector()


def get_timing_collector() -> TimingCollector | None:
    """Get the current timing collector."""
    return _timing_collector


@contextmanager
def time_operation(operation: str):
    """Time an operation if timing is enabled."""
    global _timing_collector
    if _timing_collector is not None:
        with _timing_collector.time_operation(operation):
            yield
    else:
        yield
