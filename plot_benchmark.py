#!/usr/bin/env python
"""Plot benchmark results from repo size testing."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def plot_results(json_file: str, output_file: str = "benchmark_results.png"):
    """Generate plots from benchmark JSON results."""

    with open(json_file) as f:
        data = json.load(f)

    if not data:
        print("No data to plot!")
        return

    # Sort by repo size
    data = sorted(data, key=lambda x: x["total_mb"])

    # Extract data
    repo_names = [r["repo_name"] for r in data]
    sizes_mb = [r["total_mb"] for r in data]
    # file_counts = [r["file_count"] for r in data]
    tar_times = [r["creation_time"] for r in data]
    tar_sizes = [r["tarball_size_mb"] for r in data]
    upload_times = [r["upload_time"] for r in data]
    server_times = [r["server_total_time"] for r in data]

    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Repository Size vs Operations Latency", fontsize=16, fontweight="bold"
    )

    # Plot 1: Tarball operations
    ax1 = axes[0, 0]
    ax1.scatter(
        sizes_mb, tar_times, s=100, alpha=0.6, label="Tarball Creation", color="blue"
    )
    ax1.scatter(sizes_mb, upload_times, s=100, alpha=0.6, label="Upload", color="green")

    # Add trendlines
    if len(sizes_mb) > 1:
        z1 = np.polyfit(sizes_mb, tar_times, 1)
        p1 = np.poly1d(z1)
        ax1.plot(sizes_mb, p1(sizes_mb), "b--", alpha=0.3, linewidth=2)

        z2 = np.polyfit(sizes_mb, upload_times, 1)
        p2 = np.poly1d(z2)
        ax1.plot(sizes_mb, p2(sizes_mb), "g--", alpha=0.3, linewidth=2)

    ax1.set_xlabel("Repository Size (MB)", fontsize=12)
    ax1.set_ylabel("Time (seconds)", fontsize=12)
    ax1.set_title("Tarball Operations", fontsize=13, fontweight="bold")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Server processing
    ax2 = axes[0, 1]
    ax2.scatter(sizes_mb, server_times, s=100, alpha=0.6, color="red")

    if len(sizes_mb) > 1:
        z = np.polyfit(sizes_mb, server_times, 1)
        p = np.poly1d(z)
        ax2.plot(sizes_mb, p(sizes_mb), "r--", alpha=0.3, linewidth=2)

        # Add equation
        slope = z[0]
        ax2.text(
            0.05,
            0.95,
            f"~{slope:.2f}s per MB",
            transform=ax2.transAxes,
            fontsize=10,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

    ax2.set_xlabel("Repository Size (MB)", fontsize=12)
    ax2.set_ylabel("Time (seconds)", fontsize=12)
    ax2.set_title(
        "Server Processing (extraction + analysis)", fontsize=13, fontweight="bold"
    )
    ax2.grid(True, alpha=0.3)

    # Plot 3: Compression ratio
    ax3 = axes[1, 0]
    compression_ratios = [
        tar_sizes[i] / sizes_mb[i] if sizes_mb[i] > 0 else 0 for i in range(len(data))
    ]
    ax3.bar(repo_names, compression_ratios, alpha=0.6, color="purple")
    ax3.axhline(y=1.0, color="r", linestyle="--", alpha=0.5, label="No compression")
    ax3.set_xlabel("Repository", fontsize=12)
    ax3.set_ylabel("Compression Ratio (tarball/repo)", fontsize=12)
    ax3.set_title("Compression Efficiency", fontsize=13, fontweight="bold")
    ax3.tick_params(axis="x", rotation=45)
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis="y")

    # Plot 4: Total time breakdown
    ax4 = axes[1, 1]
    width = 0.6
    x = np.arange(len(repo_names))

    # Stacked bar chart
    ax4.bar(x, tar_times, width, label="Tarball Creation", color="blue", alpha=0.7)
    ax4.bar(
        x,
        upload_times,
        width,
        bottom=tar_times,
        label="Upload",
        color="green",
        alpha=0.7,
    )
    ax4.bar(
        x,
        server_times,
        width,
        bottom=np.array(tar_times) + np.array(upload_times),
        label="Server Processing",
        color="red",
        alpha=0.7,
    )

    ax4.set_xlabel("Repository", fontsize=12)
    ax4.set_ylabel("Time (seconds)", fontsize=12)
    ax4.set_title("Total Time Breakdown", fontsize=13, fontweight="bold")
    ax4.set_xticks(x)
    ax4.set_xticklabels(repo_names, rotation=45)
    ax4.legend()
    ax4.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    print(f"Plot saved to: {output_file}")

    # Print statistics
    print("\nStatistics:")
    print(f"  Repos benchmarked: {len(data)}")
    print(f"  Size range: {min(sizes_mb):.2f} - {max(sizes_mb):.2f} MB")
    print(
        f"  Avg tarball creation: {np.mean(tar_times):.2f}s (±{np.std(tar_times):.2f}s)"
    )
    print(f"  Avg upload: {np.mean(upload_times):.2f}s (±{np.std(upload_times):.2f}s)")
    print(
        f"  Avg server processing: {np.mean(server_times):.2f}s (±{np.std(server_times):.2f}s)"
    )
    print(f"  Avg compression ratio: {np.mean(compression_ratios):.2%}")


def main():
    parser = argparse.ArgumentParser(description="Plot benchmark results")
    parser.add_argument("json_file", help="JSON file with benchmark results")
    parser.add_argument(
        "--output", default="benchmark_results.png", help="Output image file"
    )

    args = parser.parse_args()

    if not Path(args.json_file).exists():
        print(f"Error: File not found: {args.json_file}")
        return

    plot_results(args.json_file, args.output)


if __name__ == "__main__":
    main()
