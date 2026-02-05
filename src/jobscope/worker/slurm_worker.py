import os
import re
import subprocess
import sys
import time

from pathlib import Path
from rich.console import Console

from .utils import find_worker_binary, kill_zombie_steps

console = Console()

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
    factor = {"": 1.0, "K": 1.0 / 1024.0, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024.0, "P": 1024.0 * 1024.0 * 1024.0}
    return int(num * factor.get(unit, 1.0))


def _calc_cpus_per_node(num_cpus: int | None, num_nodes: int | None) -> int | None:
    if not num_cpus or not num_nodes:
        return None
    return (num_cpus + num_nodes - 1) // num_nodes


def _parse_req_mem_mb(req_mem: str, cpus_per_node: int | None, num_cpus: int | None, num_nodes: int | None) -> int | None:
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


def run_slurm_worker(output_dir: Path, period: int, jobid: str):
    """
    Checks the Slurm job status and starts the worker agent using srun if running.
    """
    try:
        # 1. Check if job is in the queue
        squeue_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%t"]
        
        with console.status(f"[bold blue]Waiting for job {jobid}...", spinner="dots") as status:
            while True:
                # We run this in a loop to wait for PENDING -> RUNNING
                result = subprocess.run(
                    squeue_cmd,
                    capture_output=True,
                    text=True
                )
                
                # If return code is non-zero, squeue likely failed or job doesn't exist
                if result.returncode != 0:
                    # squeue might return error if job finished/not found
                    console.print(f"[red]Error checking job status for {jobid}. Is it valid/still running?[/red]")
                    sys.exit(1)
                
                state = result.stdout.strip()
                
                if not state:
                     # Check if job completed recently or is invalid
                     # We can try seeing if it's in sacct or just fail
                     console.print(f"[red]Job {jobid} not found in squeue.[/red]")
                     sys.exit(1)

                if state == "R": # Running
                    break
                elif state == "PD": # Pending
                    status.update(f"[bold yellow]Job {jobid} is pending...")
                    time.sleep(DEFAULT_SLEEP)
                    continue
                elif state in ["CG", "F", "CD", "CA"]: # Completing/Failed/Completed/Cancelled
                     console.print(f"[red]Job {jobid} is in state {state}. Cannot attach worker.[/red]")
                     sys.exit(1)
                else:
                     # Other states like suspended, etc. Wait or fail? 
                     # Let's wait for now, or print info.
                     status.update(f"[bold blue]Job {jobid} is in state {state}...")
                     time.sleep(DEFAULT_SLEEP)

        # 2. Run srun
        console.print(f"[green]Job {jobid} is running. Starting worker agent...[/green]")
        
        # Get number of nodes to ensure srun launches on all of them
        nodes_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%D"]
        res_nodes = subprocess.run(nodes_cmd, capture_output=True, text=True)
        if res_nodes.returncode == 0 and res_nodes.stdout.strip():
            num_nodes = res_nodes.stdout.strip()
            console.print(f"Allocated nodes: {num_nodes}")
        else:
            console.print("[yellow]Could not determine node count. srun might default to partial allocation.[/yellow]")
            num_nodes = None
            
        # Get allocated CPUs per node to ensure agent sees all of them
        # %c = Min CPUs per node requested
        cpus_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%c"]
        res_cpus = subprocess.run(cpus_cmd, capture_output=True, text=True)
        cpus_per_node = None
        cpus_per_node_int = None
        if res_cpus.returncode == 0 and res_cpus.stdout.strip():
             cpus_out = res_cpus.stdout.strip()
             # If multiple lines or anything, take first
             cpus_per_node = cpus_out.splitlines()[0].strip()
             cpus_per_node_int = _first_int(cpus_per_node)
             console.print(f"CPUs per node: {cpus_per_node}")
        
        # Cleanup any previous agents that might be stuck
        kill_zombie_steps(jobid)

        agent_path = find_worker_binary()

        mem_total_mb = _get_job_memory_total_mb(jobid, cpus_per_node_int)
        if mem_total_mb:
            console.print(f"Allocated memory per node: {mem_total_mb} MB")

        # We want to run one agent per node allocated to the job
        # srun --jobid <jobid> --nodes=<N> --ntasks-per-node=1 --cpus-per-task=<C> <agent> ...
        
        cmd = [
            "srun",
            "--jobid", str(jobid),
            "--ntasks-per-node=1",
            "--overlap",
        ]
        
        if num_nodes:
            cmd.append(f"--nodes={num_nodes}")
            
        if cpus_per_node:
            cmd.append(f"--cpus-per-task={cpus_per_node}")

        if mem_total_mb:
            cmd.append(f"--export=ALL,JOBSCOPE_MEM_TOTAL_MB={mem_total_mb}")
            
        cmd.extend([
            agent_path,
            "--output", str(output_dir),
            "--period", str(period),
            "--mode", "slurm",
            "--continuous"
        ])

        env = os.environ.copy()
        if mem_total_mb:
            env["JOBSCOPE_MEM_TOTAL_MB"] = str(mem_total_mb)
        
        # Start srun in background. It will launch agents on compute nodes.
        srun_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env
        )
        
        console.print(f"[green]Slurm worker attached. srun PID: {srun_process.pid}[/green]")
        
        # Initial check
        time.sleep(1)
        if srun_process.poll() is not None:
             console.print("[red]Error: srun failed to start.[/red]")
             if srun_process.stderr:
                 console.print(srun_process.stderr.read().decode())
             sys.exit(1)
             
        return srun_process

    except KeyboardInterrupt:
        # Let the caller handle cleanup
        raise
    except Exception as e:
        console.print(f"[red]Failed to run slurm worker: {e}[/red]")
        sys.exit(1)
