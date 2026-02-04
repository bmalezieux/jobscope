#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

echo "Starting SLURM cluster..."
# Pull latest images just in case
docker compose pull
docker compose up -d

echo "Waiting for cluster to be healthy..."
for i in {1..30}; do
    if docker exec slurmctld scontrol ping &>/dev/null; then
        echo "Cluster is ready."
        break
    fi
    echo "Waiting..."
    sleep 2
done

# Ensure we have cargo/rust on host to build the agent first
cd ../..
if [ ! -f "jobscope-agent/target/release/jobscope-agent" ]; then
    echo "Building jobscope-agent on host..."
    cd jobscope-agent && cargo build --release && cd ..
fi

echo "Installing jobscope in slurmctld..."

# Install uv
docker exec slurmctld bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh"

# Create venv with Python 3.12 and install jobscope
docker exec slurmctld bash -c "/root/.local/bin/uv venv /root/jobscope-venv --python 3.12 && source /root/jobscope-venv/bin/activate && /root/.local/bin/uv pip install -e /jobscope"

echo "Cluster setup complete."
