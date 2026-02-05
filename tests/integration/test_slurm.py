import json
import subprocess
import time
import pytest

pytestmark = pytest.mark.slurm


def run_command(cmd, check=True):
    print(f"Running: {cmd}")
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)


def submit_and_monitor(
    nodes, tasks_per_node, cpus_per_task, gpu_config, workload_script, artifacts_dir
):
    job_id = None
    script_path = None

    try:
        # Create unique workload script
        script_path = artifacts_dir / f"workload_{time.time()}.sh"
        script_path.write_text(workload_script)

        # Build sbatch command
        cmd = "docker exec slurm-docker-cluster-slurmctld sbatch --parsable"
        cmd += f" --nodes={nodes}"
        cmd += f" --ntasks-per-node={tasks_per_node}"
        cmd += f" --cpus-per-task={cpus_per_task}"
        if gpu_config:
            cmd += f" --gpus={gpu_config}"

        container_script_path = f"/jobscope/tests/integration/.artifacts/{script_path.name}"

        cmd += f" {container_script_path}"

        res = run_command(cmd)
        job_id = res.stdout.strip()
        print(f"Submitted Job ID: {job_id}")

        # Wait for job to run
        print("Waiting for job to start...")
        started = False
        state = "UNKNOWN"
        for i in range(20):
            res = run_command(
                f"docker exec slurm-docker-cluster-slurmctld squeue --job {job_id} --noheader --format=%t"
            )
            state = res.stdout.strip()
            if state == "R":
                started = True
                break
            time.sleep(1)

        assert started, f"Job {job_id} did not start. Status: {state}"

        # Start monitoring
        summary_file = f"/jobscope/tests/integration/.artifacts/slurm_summary_{job_id}.json"
        monitor_cmd = [
            "docker",
            "exec",
            "slurm-docker-cluster-slurmctld",
            "/root/jobscope-venv/bin/python",
            "-m",
            "jobscope",
            "--jobid",
            str(job_id),
            "--period",
            "1.0",
            "--summary",
            summary_file,
            "--headless",
        ]

        print(f"Starting monitoring: {' '.join(monitor_cmd)}")
        proc = subprocess.Popen(monitor_cmd)

        # Monitor for a bit
        time.sleep(10)

        # Stop
        run_command(
            "docker exec slurm-docker-cluster-slurmctld pkill -INT -f 'python -m jobscope'"
        )
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

        # Verify
        host_summary_path = artifacts_dir / f"slurm_summary_{job_id}.json"
        assert host_summary_path.exists()

        summary = json.loads(host_summary_path.read_text())
        return summary

    finally:
        if job_id:
            run_command(
                f"docker exec slurm-docker-cluster-slurmctld scancel {job_id}",
                check=False,
            )

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
def test_slurm_resources(slurm_cluster, artifacts_dir, nodes, tasks, cpus, gpus):
    script = """#!/bin/bash
#SBATCH --job-name=resource_test
#SBATCH --output=/jobscope/tests/integration/.artifacts/out-%j.log
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
        summary = submit_and_monitor(nodes, tasks, cpus, gpu_arg, script, artifacts_dir)

        # Verification
        # 1. Cpu count
        # In slurm, --cpus-per-task=N means we should see N cpus allocated per process
        # But jobscope monitors the *allocated* CPUs for the job on that node.
        # If tasks=1, cpus=2, then allocation on node is 2.

        # Our summary has stable per-node cpu_count. This should match 'cpus' * 'tasks' (per node)
        expected_cpus_per_node = tasks * cpus

        nodes_summary = summary.get("nodes", {})
        assert nodes_summary, "Summary contains no node data"

        # Check that unique hostnames match node count
        assert len(nodes_summary) == nodes

        cpu_counts = [
            node.get("cpu_count", 0) for node in nodes_summary.values() if node
        ]
        assert cpu_counts

        for reported_cpus in cpu_counts:
            assert (
                reported_cpus == expected_cpus_per_node
            ), f"Expected {expected_cpus_per_node} CPUs, got {reported_cpus}"

    except subprocess.CalledProcessError as e:
        if "Submitted batch job" not in e.stdout and gpus > 0:
            pytest.skip(
                "Could not submit GPU job (likely no GPU configured in cluster)"
            )
        raise e
