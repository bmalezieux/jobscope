import os
import re
import subprocess
import sys
import time
from pathlib import Path

from ..logging import get_logger
from .utils import find_worker_binary, kill_zombie_steps

logger = get_logger(__name__)

DEFAULT_SLEEP = 2  # seconds


def _first_int(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    if not match:
        return None
    return int(match.group(0))


def _parse_mem_mb(value: str) -> int | None:
    raw = (value or "").strip()
    if not raw or raw == "0":
        return None
    match = re.match(r"^(?P<num>\d+(?:\.\d+)?)(?P<unit>[KMGTP]?)$", raw, re.IGNORECASE)
    if not match:
        return None
    num = float(match.group("num"))
    unit = match.group("unit").upper()
    factor = {
        "": 1.0,
        "K": 1.0 / 1024.0,
        "M": 1.0,
        "G": 1024.0,
        "T": 1024.0 * 1024.0,
        "P": 1024.0 * 1024.0 * 1024.0,
    }
    return int(num * factor.get(unit, 1.0))


def _calc_cpus_per_node(num_cpus: int | None, num_nodes: int | None) -> int | None:
    if not num_cpus or not num_nodes:
        return None
    return (num_cpus + num_nodes - 1) // num_nodes


def _parse_req_mem_mb(
    req_mem: str, cpus_per_node: int | None, num_cpus: int | None, num_nodes: int | None
) -> int | None:
    raw = (req_mem or "").strip()
    if not raw or raw == "0":
        return None
    per = None
    if raw[-1].lower() in ("c", "n"):
        per = raw[-1].lower()
        raw = raw[:-1]
    value_mb = _parse_mem_mb(raw)
    if value_mb is None:
        return None
    if per in (None, "n"):
        return value_mb
    if per == "c":
        cpus = cpus_per_node or _calc_cpus_per_node(num_cpus, num_nodes)
        if cpus:
            return value_mb * cpus
    return None


def _get_job_memory_total_mb(jobid: str, cpus_per_node: int | None) -> int | None:
    cmd = ["scontrol", "show", "job", "-o", str(jobid)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None

    fields = {}
    for token in result.stdout.strip().split():
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value

    num_cpus = _first_int(fields.get("NumCPUs", ""))
    num_nodes = _first_int(fields.get("NumNodes", ""))

    req_mem = fields.get("ReqMem", "")
    total_mb = _parse_req_mem_mb(req_mem, cpus_per_node, num_cpus, num_nodes)
    if total_mb:
        return total_mb

    mem_node = _parse_mem_mb(fields.get("MinMemoryNode", ""))
    if mem_node:
        return mem_node

    mem_cpu = _parse_mem_mb(fields.get("MinMemoryCPU", ""))
    if mem_cpu:
        cpus = cpus_per_node or _calc_cpus_per_node(num_cpus, num_nodes)
        if cpus:
            return mem_cpu * cpus

    return None


def run_slurm_worker(output_dir: Path, period: float, jobid: str):
    """
    Checks the Slurm job status and starts the worker worker using srun if running.
    """
    try:
        squeue_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%t"]

        logger.info("Waiting for job %s to start...", jobid)
        while True:
            result = subprocess.run(squeue_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(
                    "Error checking job status for %s. Is it valid/still running?",
                    jobid,
                )
                sys.exit(1)

            state = result.stdout.strip()

            if not state:
                logger.error("Job %s not found in squeue.", jobid)
                sys.exit(1)

            if state == "R":
                logger.info("Job %s detected running.", jobid)
                break
            if state in [
                "CG",
                "F",
                "CD",
                "CA",
            ]:
                logger.error(
                    "Job %s is in state %s. Cannot attach worker.", jobid, state
                )
                sys.exit(1)

            time.sleep(DEFAULT_SLEEP)

        logger.info("Job %s is running. Starting worker ...", jobid)

        nodes_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%D"]
        res_nodes = subprocess.run(nodes_cmd, capture_output=True, text=True)
        if res_nodes.returncode == 0 and res_nodes.stdout.strip():
            num_nodes = res_nodes.stdout.strip()
            logger.info("Allocated nodes: %s", num_nodes)
        else:
            logger.warning(
                "Could not determine node count. srun might default to partial allocation."
            )
            num_nodes = None

        cpus_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%c"]
        res_cpus = subprocess.run(cpus_cmd, capture_output=True, text=True)
        cpus_per_node = None
        cpus_per_node_int = None
        if res_cpus.returncode == 0 and res_cpus.stdout.strip():
            cpus_out = res_cpus.stdout.strip()
            cpus_per_node = cpus_out.splitlines()[0].strip()
            cpus_per_node_int = _first_int(cpus_per_node)
            logger.info("CPUs per node: %s", cpus_per_node)

        kill_zombie_steps(jobid)

        worker_path = find_worker_binary()

        mem_total_mb = _get_job_memory_total_mb(jobid, cpus_per_node_int)
        if mem_total_mb:
            logger.info("Allocated memory per node: %s MB", mem_total_mb)

        cmd = [
            "srun",
            "--jobid",
            str(jobid),
            "--ntasks-per-node=1",
            "--overlap",
        ]

        if num_nodes:
            cmd.append(f"--nodes={num_nodes}")

        if cpus_per_node:
            cmd.append(f"--cpus-per-task={cpus_per_node}")

        if mem_total_mb:
            cmd.append(f"--export=ALL,JOBSCOPE_MEM_TOTAL_MB={mem_total_mb}")

        cmd.extend(
            [
                worker_path,
                "--output",
                str(output_dir),
                "--period",
                str(period),
                "--mode",
                "slurm",
                "--continuous",
            ]
        )

        env = os.environ.copy()
        if mem_total_mb:
            env["JOBSCOPE_MEM_TOTAL_MB"] = str(mem_total_mb)

        srun_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env
        )

        logger.info("Slurm worker attached. srun PID: %s", srun_process.pid)

        time.sleep(1)
        if srun_process.poll() is not None:
            logger.error("srun failed to start.")
            if srun_process.stderr:
                logger.error(srun_process.stderr.read().decode())
            sys.exit(1)

        return srun_process

    except KeyboardInterrupt:
        # Let the caller handle cleanup
        raise
    except Exception as e:
        logger.error("Failed to run slurm worker: %s", e)
        sys.exit(1)
