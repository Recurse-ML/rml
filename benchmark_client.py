#!/usr/bin/env python
"""Client-side benchmark script for RML.

Measures the latency of client-side operations including:
- Tarball creation
- File collection
- Network upload
- Total end-to-end time
"""

import argparse
import asyncio
import json
import sys
import tarfile
import time
from pathlib import Path
from typing import List, Optional

import httpx


def create_tarball(
    base_dir: Path, head_dir: Path, target_files: List[str], output_path: Path
) -> dict:
    """Create a tarball with base and head directories.

    Returns timing metrics.
    """
    metrics = {
        "file_collection_time": 0.0,
        "tarball_write_time": 0.0,
        "tarball_size_bytes": 0,
        "num_files": len(target_files),
    }

    # Collect files
    collect_start = time.time()
    files_to_add = []
    for target_file in target_files:
        base_file = base_dir / target_file
        head_file = head_dir / target_file

        if base_file.exists():
            files_to_add.append(("base", base_file, target_file))
        if head_file.exists():
            files_to_add.append(("head", head_file, target_file))

    metrics["file_collection_time"] = time.time() - collect_start

    # Create tarball
    write_start = time.time()
    with tarfile.open(output_path, "w") as tar:
        for dir_name, file_path, arcname in files_to_add:
            tar.add(file_path, arcname=f"{dir_name}/{arcname}")

    metrics["tarball_write_time"] = time.time() - write_start
    metrics["tarball_size_bytes"] = output_path.stat().st_size

    return metrics


async def upload_and_analyze(
    api_url: str,
    api_key: str,
    tarball_path: Path,
    target_files: List[str],
) -> dict:
    """Upload tarball and wait for analysis results.

    Returns timing metrics and results.
    """
    metrics = {
        "upload_time": 0.0,
        "server_processing_time": 0.0,
        "polling_time": 0.0,
        "num_comments": 0,
        "status": None,
    }

    # Upload
    upload_start = time.time()
    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(tarball_path, "rb") as f:
            response = await client.post(
                f"{api_url}/api/check/",
                files={"tar_file": ("upload.tar", f, "application/x-tar")},
                data={"target_filenames": target_files},
                headers={"X-API-Key": api_key},
            )

    response.raise_for_status()
    check_id = response.json()["check_id"]
    metrics["upload_time"] = time.time() - upload_start

    # Poll for results
    polling_start = time.time()
    async with httpx.AsyncClient(timeout=300.0) as client:
        while True:
            poll_iter_start = time.time()
            response = await client.get(
                f"{api_url}/api/check/{check_id}/",
                headers={"X-API-Key": api_key},
            )
            response.raise_for_status()
            data = response.json()

            if data["status"] != "pending":
                metrics["status"] = data["status"]
                metrics["num_comments"] = len(data.get("comments", []))
                break

            # Sleep for remaining time to make 1s intervals
            elapsed = time.time() - poll_iter_start
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

    total_polling_time = time.time() - polling_start
    metrics["polling_time"] = total_polling_time

    # Estimate server processing time (subtract polling delays)
    num_polls = int(total_polling_time)
    metrics["server_processing_time"] = total_polling_time - (num_polls * 1.0)

    return metrics


async def run_benchmark(
    api_url: str,
    api_key: str,
    base_dir: Path,
    head_dir: Path,
    target_files: List[str],
    output_file: Optional[str] = None,
) -> dict:
    """Run complete benchmark from client side."""

    print("Starting benchmark...")
    print(f"  API URL: {api_url}")
    print(f"  Target files: {len(target_files)}")

    total_start = time.time()

    # Create tarball
    print("\n[1/3] Creating tarball...")
    tarball_path = Path("/tmp/rml_benchmark.tar")
    tarball_metrics = create_tarball(base_dir, head_dir, target_files, tarball_path)
    print(f"  ✓ Tarball created: {tarball_metrics['tarball_size_bytes'] / 1024:.1f} KB")
    print(f"    - File collection: {tarball_metrics['file_collection_time']:.3f}s")
    print(f"    - Tarball write: {tarball_metrics['tarball_write_time']:.3f}s")

    # Upload and analyze
    print("\n[2/3] Uploading and analyzing...")
    upload_metrics = await upload_and_analyze(
        api_url, api_key, tarball_path, target_files
    )
    print(f"  ✓ Analysis complete: {upload_metrics['num_comments']} comments found")
    print(f"    - Upload time: {upload_metrics['upload_time']:.3f}s")
    print(f"    - Server processing: {upload_metrics['server_processing_time']:.3f}s")
    print(f"    - Polling time: {upload_metrics['polling_time']:.3f}s")

    total_time = time.time() - total_start

    # Combine results
    results = {
        "total_time": total_time,
        "tarball_metrics": tarball_metrics,
        "upload_metrics": upload_metrics,
        "breakdown": {
            "client_tarball_creation": tarball_metrics["file_collection_time"]
            + tarball_metrics["tarball_write_time"],
            "network_upload": upload_metrics["upload_time"],
            "server_processing": upload_metrics["server_processing_time"],
            "polling_overhead": upload_metrics["polling_time"]
            - upload_metrics["server_processing_time"],
        },
    }

    # Clean up
    tarball_path.unlink()

    # Print summary
    print(f"\n{'=' * 80}")
    print("BENCHMARK RESULTS")
    print(f"{'=' * 80}")
    print(f"Total time: {results['total_time']:.2f}s")
    print("\nBreakdown:")
    for component, duration in results["breakdown"].items():
        percentage = (duration / results["total_time"]) * 100
        print(f"  {component:30s}: {duration:6.2f}s ({percentage:5.1f}%)")
    print(
        f"\nTarball size: {results['tarball_metrics']['tarball_size_bytes'] / 1024:.1f} KB"
    )
    print(f"Comments found: {results['upload_metrics']['num_comments']}")
    print(f"Status: {results['upload_metrics']['status']}")
    print(f"{'=' * 80}\n")

    # Save to file
    if output_file:
        output_path = Path(output_file)
        output_path.write_text(json.dumps(results, indent=2))
        print(f"Results saved to {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark RML client-side performance"
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8080", help="API base URL"
    )
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument(
        "--base-dir",
        required=True,
        type=Path,
        help="Base directory with original files",
    )
    parser.add_argument(
        "--head-dir",
        required=True,
        type=Path,
        help="Head directory with modified files",
    )
    parser.add_argument(
        "--files", required=True, nargs="+", help="Target files to analyze"
    )
    parser.add_argument("--output", help="Output file for results (JSON)")

    args = parser.parse_args()

    # Validate directories
    if not args.base_dir.exists():
        print(f"Error: Base directory does not exist: {args.base_dir}")
        sys.exit(1)
    if not args.head_dir.exists():
        print(f"Error: Head directory does not exist: {args.head_dir}")
        sys.exit(1)

    # Run benchmark
    try:
        results = asyncio.run(
            run_benchmark(
                api_url=args.api_url,
                api_key=args.api_key,
                base_dir=args.base_dir,
                head_dir=args.head_dir,
                target_files=args.files,
                output_file=args.output,
            )
        )

        # Exit with success if analysis completed
        if results["upload_metrics"]["status"] == "completed":
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
