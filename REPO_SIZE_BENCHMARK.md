# Repository Size Benchmarking

Benchmark how tarball operations and analysis scale with repository size.

## Overview

This benchmark suite measures:
1. **Tarball creation time** vs repo size
2. **Upload time** vs repo size  
3. **Server processing time** (extraction + analysis) vs repo size
4. Compression ratios
5. Total time breakdown

The goal is to understand how the pipeline scales and identify size-related bottlenecks.

## Setup

### Prerequisites

```bash
# Install matplotlib for plotting
cd /Users/v.i/Desktop/repos/rml
pip install matplotlib numpy
```

### Server Running

Make sure your server is running (see BENCHMARKING_QUICK_START.md):

```bash
# Terminal 1: Redis
redis-server redis.conf

# Terminal 2: Worker  
cd /Users/v.i/Desktop/repos/squash
export ENV=dev && source .recurse_env
python src/squash/worker.py

# Terminal 3: API
cd /Users/v.i/Desktop/repos/squash
export ENV=dev && source .recurse_env
python src/squash/endpoints/app.py
```

## Running the Benchmark

### Option 1: Auto-discover Repos (Default)

The script will automatically find repos in `/Users/v.i/Desktop/repos/`:

```bash
cd /Users/v.i/Desktop/repos/rml

python benchmark_repo_sizes.py \
    --api-url http://localhost:8080 \
    --api-key YOUR_API_KEY \
    --output results.json
```

### Option 2: Specify Repos

Benchmark specific repositories:

```bash
python benchmark_repo_sizes.py \
    --api-url http://localhost:8080 \
    --api-key YOUR_API_KEY \
    --repos /path/to/repo1 /path/to/repo2 /path/to/repo3 \
    --output results.json
```

### Tips for Getting Varied Sizes

To get a good size distribution, you can:

**1. Clone some popular repos of different sizes:**

```bash
cd /tmp

# Small (~5 MB, ~100 files)
git clone https://github.com/pallets/flask --depth 1

# Medium (~20 MB, ~500 files)  
git clone https://github.com/fastapi/fastapi --depth 1

# Large (~50 MB, ~1000+ files)
git clone https://github.com/django/django --depth 1

# Very Large (~100+ MB, ~2000+ files)
git clone https://github.com/pytorch/pytorch --depth 1
```

Then benchmark them:

```bash
python benchmark_repo_sizes.py \
    --api-key YOUR_API_KEY \
    --repos /tmp/flask /tmp/fastapi /tmp/django /tmp/pytorch
```

**2. Or use subdirectories of existing repos:**

```bash
# Benchmark different parts of squash
python benchmark_repo_sizes.py \
    --api-key YOUR_API_KEY \
    --repos \
        /Users/v.i/Desktop/repos/squash/src \
        /Users/v.i/Desktop/repos/squash \
        /Users/v.i/Desktop/repos/rml
```

## Output

### Console Output

You'll see progress for each repo:

```
================================================================================
Benchmarking: squash
================================================================================
  [1/5] Measuring repository size...
    → 245 files, 15.3 MB
  [2/5] Preparing base and head directories...
    → Prepared in 0.45s
  [3/5] Creating tarball...
    → Created in 2.34s (12.1 MB)
  [4/5] Uploading and analyzing...
    → Upload: 3.21s
    → Server processing: 45.67s
    → Comments found: 3

  Summary:
    Repo size: 15.3 MB (245 files)
    Tarball creation: 2.34s
    Tarball size: 12.1 MB
    Upload: 3.21s
    Server total: 45.67s
```

### Summary Table

```
SUMMARY TABLE
========================================================================================================================
Repo                 Size (MB)    Files    Tar Time    Tar Size (MB)  Upload    Server    
------------------------------------------------------------------------------------------------------------------------
rml                  2.45         89       0.23s       1.89           0.45s     12.34s    
flask                5.12         156      0.45s       3.21           0.67s     18.92s    
squash               15.30        245      2.34s       12.10          3.21s     45.67s    
django               52.40        1234     8.91s       38.45          12.34s    156.78s   
========================================================================================================================
```

### JSON Output

Results are saved to `results.json`:

```json
[
  {
    "repo_name": "rml",
    "repo_path": "/Users/v.i/Desktop/repos/rml",
    "file_count": 89,
    "total_bytes": 2568192,
    "total_mb": 2.45,
    "creation_time": 0.234,
    "tarball_size_bytes": 1982464,
    "tarball_size_mb": 1.89,
    "upload_time": 0.456,
    "server_total_time": 12.345,
    "num_comments": 2,
    "status": "completed"
  },
  ...
]
```

## Plotting Results

### Generate Graphs

```bash
python plot_benchmark.py results.json --output benchmark_graph.png
```

This creates a 4-panel graph showing:

1. **Top Left**: Tarball creation & upload time vs repo size (with trendlines)
2. **Top Right**: Server processing time vs repo size (shows latency growth)
3. **Bottom Left**: Compression ratios by repo
4. **Bottom Right**: Stacked bar chart of total time breakdown

### Example Output

The plot shows:
- Linear relationship between repo size and tarball creation (~0.15s per MB)
- Upload time scaling (network dependent)
- Server processing time (extraction + bug localization)
- Compression efficiency (typically 70-80%)

## Interpreting Results

### What to Look For

1. **Tarball Creation Time**
   - Should scale roughly linearly with repo size
   - If >0.5s per MB, disk I/O might be slow

2. **Upload Time**
   - Depends on network speed and tarball size
   - If >0.3s per MB, network is the bottleneck

3. **Server Processing Time**
   - Includes extraction + bug localization
   - Extract server logs to see detailed breakdown
   - If extraction >20% of server time, it's a bottleneck

4. **Compression Ratio**
   - Should be 0.6-0.8 (60-80% of original size)
   - Lower is better
   - Text files compress well, binaries don't

### Server-Side Breakdown

Check the worker logs for detailed timing:

```bash
tail -f /Users/v.i/Desktop/repos/squash/logs/squash-*.log | grep -A 100 "LATENCY BENCHMARK REPORT"
```

You'll see the breakdown:
- Tarball extraction: ~1-5s
- Diff computation: ~0.5-2s  
- Bug localization: ~10-180s (main component)

## Optimization Ideas

Based on results, you might consider:

1. **If tarball creation is slow**:
   - Use faster compression (e.g., `-z` → `-j` for bzip2)
   - Or no compression for local networks
   - Stream files instead of tarballing

2. **If upload is slow**:
   - Use compression
   - Send only changed files (incremental)
   - Consider delta/patch uploads

3. **If server extraction is slow**:
   - Extract to local disk instead of NFS
   - Use faster decompression
   - Consider extracting only needed files

4. **If server processing grows nonlinearly**:
   - There's likely an O(n²) operation somewhere
   - Check bug localizer for scaling issues

## Example Full Run

```bash
# 1. Clone test repos
cd /tmp
git clone --depth 1 https://github.com/pallets/flask
git clone --depth 1 https://github.com/fastapi/fastapi

# 2. Run benchmark
cd /Users/v.i/Desktop/repos/rml
python benchmark_repo_sizes.py \
    --api-key $SQUASH_API_KEY \
    --repos /tmp/flask /tmp/fastapi /Users/v.i/Desktop/repos/rml \
    --output repo_size_results.json

# 3. Generate plot
python plot_benchmark.py repo_size_results.json

# 4. View results
open benchmark_results.png
```

## Combining with Regular Benchmarks

You can combine this with regular latency benchmarking:

```bash
# 1. Test repo size scaling
python benchmark_repo_sizes.py --api-key $KEY --output size_results.json

# 2. Run normal analysis with timing
python3 src/rml/__init__.py some_file.py

# 3. Check server logs for detailed breakdown
tail -f /Users/v.i/Desktop/repos/squash/logs/squash-*.log | grep LATENCY
```

This gives you:
- **Repo size benchmark**: How operations scale
- **Regular run**: Detailed per-operation timing
- **Server logs**: Complete breakdown of where time goes

Together, these help you understand both scaling behavior and specific bottlenecks!

