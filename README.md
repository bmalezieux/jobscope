# JobScope

A system resource monitoring tool for compute clusters that tracks CPU, GPU, and process metrics in real-time with a beautiful terminal UI.

## Description

JobScope is a hybrid Python/Rust application designed for monitoring computational workloads both locally and on SLURM clusters. It collects metrics on CPU usage, GPU utilization (NVIDIA), memory consumption, and process-level statistics, displaying them in an interactive terminal interface or exporting them to Parquet files for analysis.

The monitoring agent is written in Rust for performance and low overhead, while the CLI and TUI are implemented in Python for ease of use.

## Installation

### Requirements

- **Rust toolchain**: Required for building the monitoring agent (install from [rustup.rs](https://rustup.rs/))
- **Python**: >=3.12
- **CUDA/NVIDIA drivers**: Optional, only needed for GPU monitoring

### Install with uv (Recommended)

Since JobScope uses [Maturin](https://www.maturin.rs/) to build Rust bindings, you need the Rust toolchain installed before installation.

```bash
# Install Rust first (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install jobscope with uv
uv pip install jobscope
```

Or install directly from the repository:

```bash
# Clone the repository
git clone <repository-url>
cd jobscope

# Install with uv
uv pip install .
```

### Install with pip

```bash
# Ensure Rust is installed
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install with pip
pip install jobscope
```

Or from the repository:

```bash
pip install .
```

The Maturin build backend automatically compiles the Rust agent binary during the Python package installation process, making it available as part of the Python package.

## Usage

### Local Monitoring

Monitor your local machine's resources in real-time:

```bash
# Start interactive monitoring with default 2-second refresh
jobscope

# Custom refresh period (in seconds)
jobscope --period 1.0

# Run once and exit (no continuous monitoring)
jobscope --once

# Export metrics to Parquet file
jobscope --parquet ./metrics.parquet
```

The TUI displays:

- **CPU usage** per core
- **GPU utilization** and memory (NVIDIA only)
- **Process information** (top consumers by CPU/memory)
- Real-time updates at the specified refresh period

Press `Ctrl+q` to stop monitoring and clean up.

### SLURM Cluster Monitoring

Monitor a running SLURM job by attaching to it with its job ID:

```bash
# Monitor a specific SLURM job
jobscope --jobid 123456

# Monitor with custom period and export to Parquet
jobscope --jobid 123456 --period 5.0 --parquet ./job_123456_metrics.parquet
```

**How it works:**

- JobScope uses `squeue` to check the job status
- If the job is pending, it waits for it to start
- Once running, it uses `srun` to launch the monitoring agent on the compute node(s) allocated to your job
- Metrics are collected from the actual compute nodes and streamed back to your terminal
- Data is cleaned up automatically when you exit

## Example Workflow

```bash
# Submit a SLURM job
sbatch my_training_script.sh
# Output: Submitted batch job 789012

# Monitor the job in real-time
jobscope --jobid 789012 --parquet ./training_metrics.parquet

# After the job completes, analyze the metrics
# The Parquet file contains timestamped CPU, GPU, and process data
```

## Development

To build from source:

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Build the Rust agent manually
cd jobscope-agent
cargo build --release

# Run the Python CLI
python -m jobscope
```

## License

See LICENSE file for details.
