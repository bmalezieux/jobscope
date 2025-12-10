import subprocess
import sys
import time

from pathlib import Path

from .utils import find_worker_binary


def run_local_worker(output_dir: Path, period: int):
    try:
        agent_path = find_worker_binary()
        print(f"Starting worker: {agent_path}")
        
        cmd = [
            agent_path,
            "--output", str(output_dir),
            "--period", str(period),
            "--continuous"
        ]
        
        # Start agent in background
        agent_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        print(f"Worker started with PID {agent_process.pid}")
        
        # Give it a moment to start
        time.sleep(0.5)
        
        if agent_process.poll() is not None:
            print("Error: Agent failed to start immediately.")
            print(agent_process.stderr.read().decode())
            sys.exit(1)
            
    except Exception as e:
        print(f"Failed to start agent: {e}")
        sys.exit(1)

    return agent_process