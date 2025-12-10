import subprocess
import sys
import time

from pathlib import Path

from .utils import find_worker_binary


def run_slurm_worker(output_dir: Path, period: int, jobid: int):
    """
    Checks the Slurm job status and starts the worker agent using srun if running.
    """
    try:
        # 1. Check if job is in the queue
        squeue_cmd = ["squeue", "--job", str(jobid), "--noheader", "--format=%t"]
        
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
                print(f"Error checking job status for {jobid}. Is it valid/still running?")
                sys.exit(1)
            
            state = result.stdout.strip()
            
            if not state:
                 # Check if job completed recently or is invalid
                 # We can try seeing if it's in sacct or just fail
                 print(f"Job {jobid} not found in squeue.")
                 sys.exit(1)

            if state == "R": # Running
                break
            elif state == "PD": # Pending
                print(f"Job {jobid} is Pending. Waiting...")
                time.sleep(2)
                continue
            elif state in ["CG", "F", "CD", "CA"]: # Completing/Failed/Completed/Cancelled
                 print(f"Job {jobid} is in state {state}. Cannot attach worker.")
                 sys.exit(1)
            else:
                 # Other states like suspended, etc. Wait or fail? 
                 # Let's wait for now, or print info.
                 print(f"Job {jobid} is in state {state}. Waiting...")
                 time.sleep(2)

        # 2. Run srun
        print(f"Job {jobid} is running. Starting worker agent...")
        agent_path = find_worker_binary()
        
        # We want to run one agent per node allocated to the job
        # srun --jobid <jobid> --ntasks-per-node=1 <agent> ...
        
        cmd = [
            "srun",
            "--jobid", str(jobid),
            "--ntasks-per-node=1",
            agent_path,
            "--output", str(output_dir),
            "--period", str(period),
            "--continuous"
        ]
        
        # Start srun in background. It will launch agents on compute nodes.
        srun_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        print(f"Slurm worker attached. srun PID: {srun_process.pid}")
        
        # Initial check
        time.sleep(1)
        if srun_process.poll() is not None:
             print("Error: srun failed to start.")
             print(srun_process.stderr.read().decode())
             sys.exit(1)
             
        return srun_process

    except KeyboardInterrupt:
        # Let the caller handle cleanup
        raise
    except Exception as e:
        print(f"Failed to run slurm worker: {e}")
        sys.exit(1)