import subprocess
import time
from pathlib import Path

import pytest

# Paths
INTEGRATION_DIR = Path(__file__).parent
WORKSPACE_DIR = INTEGRATION_DIR.parent.parent
SLURM_CLUSTER_DIR = WORKSPACE_DIR / "slurm-docker-cluster"


def run_command(cmd, check=True):
    print(f"Running: {cmd}")
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)


@pytest.fixture(scope="module")
def slurm_cluster():
    """Ensure SLURM cluster is running and ready."""
    # Check if slurmctld is running
    res = run_command(
        "docker ps --filter name=slurmctld --format '{{.Status}}'", check=False
    )
    if "Up" not in res.stdout:
        pytest.skip(
            "SLURM cluster not running. Run tests/integration/start_cluster.sh first."
        )

    # Check for sufficient CPU resources
    import multiprocessing

    cpu_count = multiprocessing.cpu_count()
    if cpu_count < 2:
        pytest.skip(
            f"Ideally we need at least 2 CPUs for testing, found {cpu_count}. Skipping integration tests that require multiple CPUs."
        )

    yield


def submit_and_monitor(
    nodes, tasks_per_node, cpus_per_task, gpu_config, workload_script
):
    job_id = None
    script_path = None

    try:
        # Create unique workload script
        script_path = INTEGRATION_DIR / f"workload_{time.time()}.sh"
        script_path.write_text(workload_script)

        # Build sbatch command
        cmd = "docker exec slurmctld sbatch --parsable"
        cmd += f" --nodes={nodes}"
        cmd += f" --ntasks-per-node={tasks_per_node}"
        cmd += f" --cpus-per-task={cpus_per_task}"
        if gpu_config:
            cmd += f" --gpus={gpu_config}"

        container_script_path = f"/jobscope/tests/integration/{script_path.name}"

        cmd += f" {container_script_path}"

        res = run_command(cmd)
        job_id = res.stdout.strip()
        print(f"Submitted Job ID: {job_id}")

        # Wait for job to run
        print("Waiting for job to start...")
        started = False
        for i in range(20):
            res = run_command(
                f"docker exec slurmctld squeue --job {job_id} --noheader --format=%t"
            )
            state = res.stdout.strip()
            if state == "R":
                started = True
                break
            time.sleep(1)

        assert started, f"Job {job_id} did not start. Status: {state}"

        # Start monitoring
        metrics_file = f"/jobscope/slurm_metrics_{job_id}.parquet"
        monitor_cmd_str = f"docker exec slurmctld /root/jobscope-venv/bin/python -m jobscope --jobid {job_id} --period 1.0 --parquet {metrics_file} --headless"

        print(f"Starting monitoring: {monitor_cmd_str}")
        proc = subprocess.Popen(monitor_cmd_str.split())

        # Monitor for a bit
        time.sleep(10)

        # Stop
        run_command("docker exec slurmctld pkill -INT -f 'python -m jobscope'")
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

        # Verify
        host_parquet_path = WORKSPACE_DIR / f"slurm_metrics_{job_id}.parquet"
        assert host_parquet_path.exists()

        import pandas as pd

        df = pd.read_parquet(host_parquet_path)
        return df

    finally:
        if job_id:
            run_command(f"docker exec slurmctld scancel {job_id}", check=False)

        if script_path and script_path.exists():
            script_path.unlink()


@pytest.mark.parametrize(
    "nodes,tasks,cpus,gpus",
    [
        (1, 1, 1, 0),  # 1 node, 1 task, 1 cpu
        (1, 1, 2, 0),  # 1 node, 1 task, 2 cpus
        (2, 1, 1, 0),  # 2 nodes, 1 task/node, 1 cpu/task
    ],
)
def test_slurm_resources(slurm_cluster, nodes, tasks, cpus, gpus):
    script = """#!/bin/bash
#SBATCH --job-name=resource_test
#SBATCH --output=/jobscope/out-%j.log
#SBATCH --time=00:05:00

echo "Running on $(hostname) with $(cat /proc/self/status | grep Cpus_allowed_list)"
sleep 30
"""

    # GPU requests in Slurm often use --gpus-per-node or just --gpus
    # Our mocked cluster might not strictly enforce GPU availability if hardware is missing,
    # or it might reject the job.
    # We will simulate GPU request if asked, but verify if execution is possible.
    gpu_arg = f"{gpus}" if gpus > 0 else None

    try:
        df = submit_and_monitor(nodes, tasks, cpus, gpu_arg, script)

        # Verification
        # 1. Cpu count
        # In slurm, --cpus-per-task=N means we should see N cpus allocated per process
        # But jobscope monitors the *allocated* CPUs for the job on that node.
        # If tasks=1, cpus=2, then allocation on node is 2.

        # Our dataframe has 'cpu_count'. This should match 'cpus' * 'tasks' (per node)
        expected_cpus_per_node = tasks * cpus

        # Filter out 0 (startup artifacts)
        df = df[df["cpu_count"] > 0]

        assert not df.empty

        # Check that unique hostnames match node count
        assert df["hostname"].nunique() == nodes

        # Check cpu count
        # We allow a small deviation if transient, but mostly it should be exact.
        # We take the mode or max or verify equality
        reported_cpus = df["cpu_count"].mode()[0]
        assert (
            reported_cpus == expected_cpus_per_node
        ), f"Expected {expected_cpus_per_node} CPUs, got {reported_cpus}"

    except subprocess.CalledProcessError as e:
        if "Submitted batch job" not in e.stdout and gpus > 0:
            pytest.skip(
                "Could not submit GPU job (likely no GPU configured in cluster)"
            )
        raise e
