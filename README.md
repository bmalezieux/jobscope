# JobScope

JobScope is a CLI/TUI that shows live CPU, GPU, memory, and process metrics for local machines and Slurm jobs. It combines a Rust monitoring agent with a Python interface for responsive, low-overhead monitoring.

## Features

- Live terminal UI with per-core CPU, GPU, memory, and process stats
- Works locally or by attaching to a Slurm job
- Optional JSON summary export on exit

## Requirements

- Python 3.10+
- Rust toolchain (required to build the monitoring worker)

## Installation

From source:

```bash
git clone <repo-url>
cd jobscope

# Ensure Rust is installed
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install the package
pip install .
```

## Usage

Local monitoring:

```bash
jobscope
jobscope --period 1.0
jobscope --once
jobscope --summary ./metrics-summary.json
```

Slurm monitoring:

```bash
jobscope --jobid 123456
jobscope --jobid 123456 --period 5.0 --summary ./job_123456_summary.json
```

Notes:

- JobScope waits for pending jobs, then runs the agent on allocated nodes via `srun`.
- Press `q` to quit the UI.

## Development

```bash
uv pip install -e ".[dev]"

# Build the Rust agent manually
cd jobscope-agent
cargo build --release
```

## License

See `LICENSE` for details.
