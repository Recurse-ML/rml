#!/usr/bin/env python
"""Benchmark tarball operations and analysis against repos of different sizes.

This script:
1. Tests multiple repos of varying sizes
2. Measures tarball creation, upload, extraction separately
3. Measures bug localization time
4. Outputs data for plotting

Usage:
    python benchmark_repo_sizes.py --api-url http://localhost:8080 --api-key YOUR_KEY
"""

import argparse
import asyncio
import json
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx


def get_repo_size(repo_path: Path) -> Dict[str, int]:
    """Get repository size metrics."""
    file_count = 0
    total_bytes = 0

    for file_path in repo_path.rglob("*"):
        if file_path.is_file() and not any(
            part.startswith(".") for part in file_path.parts
        ):
            try:
                file_count += 1
                total_bytes += file_path.stat().st_size
            except (OSError, PermissionError):
                pass

    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
    }


def create_tarball_from_dir(
    base_dir: Path, head_dir: Path, output_path: Path
) -> Dict[str, Any]:
    """Create tarball and measure timing."""
    start = time.time()

    with tarfile.open(output_path, "w:gz") as tar:
        if base_dir.exists():
            tar.add(base_dir, arcname="base")
        if head_dir.exists():
            tar.add(head_dir, arcname="head")

    creation_time = time.time() - start
    tarball_size = output_path.stat().st_size

    return {
        "creation_time": creation_time,
        "tarball_size_bytes": tarball_size,
        "tarball_size_mb": round(tarball_size / (1024 * 1024), 2),
    }


async def upload_and_analyze(
    api_url: str,
    api_key: str,
    tarball_path: Path,
    target_files: List[str],
) -> Dict[str, Any]:
    """Upload tarball and wait for analysis."""

    # Upload
    upload_start = time.time()
    async with httpx.AsyncClient(timeout=600.0) as client:
        with open(tarball_path, "rb") as f:
            response = await client.post(
                f"{api_url}/api/check/",
                files={"tar_file": ("upload.tar.gz", f, "application/gzip")},
                data={"target_filenames": target_files},
                headers={
                    "Authorization": f"Bearer {api_key}"
                },  # Match rml client auth format
            )

    response.raise_for_status()
    response_data = response.json()

    # Debug: print response if check_id is missing
    if "check_id" not in response_data:
        print("Error: API response missing 'check_id'")
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response_data}")
        raise ValueError(f"API response missing check_id: {response_data}")

    check_id = response_data["check_id"]
    upload_time = time.time() - upload_start

    # Poll for results (this includes server processing)
    polling_start = time.time()
    async with httpx.AsyncClient(timeout=600.0) as client:
        while True:
            response = await client.get(
                f"{api_url}/api/check/{check_id}/",
                headers={
                    "Authorization": f"Bearer {api_key}"
                },  # Match rml client auth format
            )
            response.raise_for_status()
            data = response.json()

            if data["status"] != "pending":
                break

            await asyncio.sleep(1)

    total_polling = time.time() - polling_start

    return {
        "upload_time": upload_time,
        "server_total_time": total_polling,  # Includes extraction + analysis
        "num_comments": len(data.get("comments", [])),
        "status": data["status"],
    }


async def benchmark_repo(
    repo_path: Path,
    api_url: str,
    api_key: str,
    target_files: List[str],
    repo_name: str,
) -> Dict[str, Any]:
    """Benchmark a single repository."""

    print(f"\n{'=' * 80}")
    print(f"Benchmarking: {repo_name}")
    print(f"{'=' * 80}")

    # Measure repo size
    print("  [1/5] Measuring repository size...")
    size_metrics = get_repo_size(repo_path)
    print(f"    → {size_metrics['file_count']} files, {size_metrics['total_mb']} MB")

    # Create temp directories for base and head
    temp_dir = Path(tempfile.mkdtemp(prefix=f"benchmark_{repo_name}_"))
    base_dir = temp_dir / "base"
    head_dir = temp_dir / "head"
    base_dir.mkdir(parents=True)
    head_dir.mkdir(parents=True)

    # Copy repo to both base and head (simulating changes)
    print("  [2/5] Preparing base and head directories...")
    copy_start = time.time()

    import shutil

    for item in repo_path.iterdir():
        if item.name.startswith("."):
            continue
        if item.is_dir():
            shutil.copytree(
                item,
                base_dir / item.name,
                ignore=shutil.ignore_patterns(".*", "__pycache__", "*.pyc"),
            )
            shutil.copytree(
                item,
                head_dir / item.name,
                ignore=shutil.ignore_patterns(".*", "__pycache__", "*.pyc"),
            )
        else:
            shutil.copy2(item, base_dir / item.name)
            shutil.copy2(item, head_dir / item.name)

    prep_time = time.time() - copy_start
    print(f"    → Prepared in {prep_time:.2f}s")

    # Auto-detect Python files and make a small change to create a diff
    if target_files == ["README.md"]:
        # Find a Python file to analyze
        py_files = list(head_dir.rglob("*.py"))
        if py_files:
            # Use the first Python file
            target_file = py_files[0]
            target_files = [str(target_file.relative_to(head_dir))]

            # Make a small change (add a comment at the end)
            with open(target_file, "a") as f:
                f.write("\n# Benchmark modification\n")

            print(f"    → Auto-selected and modified: {target_files[0]}")
        else:
            print("    → Warning: No Python files found, using README.md")
            target_files = ["README.md"]
            # Create a README if it doesn't exist
            readme_path = head_dir / "README.md"
            if not readme_path.exists():
                readme_path.write_text("# Benchmark README\n")

    # Create tarball
    print("  [3/5] Creating tarball...")
    tarball_path = temp_dir / f"{repo_name}.tar.gz"
    tarball_metrics = create_tarball_from_dir(base_dir, head_dir, tarball_path)
    print(
        f"    → Created in {tarball_metrics['creation_time']:.2f}s ({tarball_metrics['tarball_size_mb']} MB)"
    )

    # Upload and analyze
    print("  [4/5] Uploading and analyzing...")
    upload_metrics = await upload_and_analyze(
        api_url, api_key, tarball_path, target_files
    )
    print(f"    → Upload: {upload_metrics['upload_time']:.2f}s")
    print(f"    → Server processing: {upload_metrics['server_total_time']:.2f}s")
    print(f"    → Comments found: {upload_metrics['num_comments']}")

    # Clean up
    print("  [5/5] Cleaning up...")
    shutil.rmtree(temp_dir)

    # Combine results
    result = {
        "repo_name": repo_name,
        "repo_path": str(repo_path),
        "timestamp": datetime.now().isoformat(),
        **size_metrics,
        **tarball_metrics,
        **upload_metrics,
    }

    print("\n  Summary:")
    print(
        f"    Repo size: {size_metrics['total_mb']} MB ({size_metrics['file_count']} files)"
    )
    print(f"    Tarball creation: {tarball_metrics['creation_time']:.2f}s")
    print(f"    Tarball size: {tarball_metrics['tarball_size_mb']} MB")
    print(f"    Upload: {upload_metrics['upload_time']:.2f}s")
    print(f"    Server total: {upload_metrics['server_total_time']:.2f}s")

    return result


async def run_benchmark_suite(
    repos: List[tuple[Path, str, List[str]]],  # (path, name, target_files)
    api_url: str,
    api_key: str,
    output_file: str,
):
    """Run benchmark on multiple repos."""

    results = []

    for repo_path, repo_name, target_files in repos:
        if not repo_path.exists():
            print(f"Skipping {repo_name} - path does not exist: {repo_path}")
            continue

        try:
            result = await benchmark_repo(
                repo_path, api_url, api_key, target_files, repo_name
            )
            results.append(result)
        except Exception as e:
            print(f"Error benchmarking {repo_name}: {e}")
            import traceback

            traceback.print_exc()

    # Save results
    output_path = Path(output_file)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\n{'=' * 80}")
    print(f"Results saved to: {output_path}")
    print(f"{'=' * 80}")

    # Print summary table
    print("\nSUMMARY TABLE")
    print("=" * 120)
    print(
        f"{'Repo':<20} {'Size (MB)':<12} {'Files':<8} {'Tar Time':<12} {'Tar Size (MB)':<14} {'Upload':<10} {'Server':<10}"
    )
    print("-" * 120)

    for result in sorted(results, key=lambda x: x["total_mb"]):
        print(
            f"{result['repo_name']:<20} "
            f"{result['total_mb']:<12.2f} "
            f"{result['file_count']:<8} "
            f"{result['creation_time']:<12.2f}s "
            f"{result['tarball_size_mb']:<14.2f} "
            f"{result['upload_time']:<10.2f}s "
            f"{result['server_total_time']:<10.2f}s"
        )

    print("=" * 120)

    # Generate plotting instructions
    print("\nTo plot the results:")
    print("```python")
    print("import json")
    print("import matplotlib.pyplot as plt")
    print()
    print(f"with open('{output_file}') as f:")
    print("    data = json.load(f)")
    print()
    print("sizes = [r['total_mb'] for r in data]")
    print("tar_times = [r['creation_time'] for r in data]")
    print("upload_times = [r['upload_time'] for r in data]")
    print("server_times = [r['server_total_time'] for r in data]")
    print()
    print("plt.figure(figsize=(12, 6))")
    print("plt.subplot(1, 2, 1)")
    print("plt.scatter(sizes, tar_times, label='Tarball Creation')")
    print("plt.scatter(sizes, upload_times, label='Upload')")
    print("plt.xlabel('Repo Size (MB)')")
    print("plt.ylabel('Time (seconds)')")
    print("plt.title('Tarball Operations vs Repo Size')")
    print("plt.legend()")
    print("plt.grid(True)")
    print()
    print("plt.subplot(1, 2, 2)")
    print("plt.scatter(sizes, server_times)")
    print("plt.xlabel('Repo Size (MB)')")
    print("plt.ylabel('Time (seconds)')")
    print("plt.title('Server Processing vs Repo Size')")
    print("plt.grid(True)")
    print()
    print("plt.tight_layout()")
    print("plt.savefig('benchmark_results.png')")
    print("print('Plot saved to benchmark_results.png')")
    print("```")


def discover_repos() -> List[tuple[Path, str, List[str]]]:
    """Discover available repos to benchmark."""

    repos = []

    # RML repo (small)
    rml_path = Path("/Users/v.i/Desktop/repos/rml")
    if rml_path.exists():
        repos.append((rml_path, "rml", ["src/rml/__init__.py"]))

    # Squash repo (medium)
    squash_path = Path("/Users/v.i/Desktop/repos/squash")
    if squash_path.exists():
        repos.append((squash_path, "squash", ["src/squash/bug_localizer.py"]))

    # Add more repos if they exist
    # You can add paths to other repos here

    return repos


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark repo size vs tarball/analysis latency"
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8080", help="API base URL"
    )
    parser.add_argument("--api-key", required=True, help="API key")
    parser.add_argument(
        "--output", default="benchmark_repo_sizes.json", help="Output JSON file"
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        help="Repo paths to benchmark (auto-discovers if not provided)",
    )

    args = parser.parse_args()

    # Discover or use provided repos
    if args.repos:
        repos = [(Path(r), Path(r).name, ["README.md"]) for r in args.repos]
    else:
        repos = discover_repos()
        if not repos:
            print("No repos found to benchmark. Provide --repos argument.")
            sys.exit(1)

    print(f"Will benchmark {len(repos)} repos:")
    for path, name, files in repos:
        print(f"  - {name}: {path}")

    # Run benchmark
    asyncio.run(run_benchmark_suite(repos, args.api_url, args.api_key, args.output))


if __name__ == "__main__":
    main()
