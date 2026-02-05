import shutil
import subprocess
from pathlib import Path


def find_worker_binary() -> str:
    """
    Find the installed Rust worker executable.

    We only need this on the login/head node. The *absolute* path we get
    will be passed to srun, so the compute nodes don't need Python.
    """
    # 1. Check development path first
    # We are in src/jobscope/worker/utils.py
    # root is 3 levels up from src/jobscope/worker
    root = Path(__file__).resolve().parent.parent.parent.parent
    dev_path = root / "jobscope-agent" / "target" / "release" / "jobscope-agent"
    if dev_path.exists():
        return str(dev_path)

    # 2. Check PATH
    worker = shutil.which("jobscope-agent")
    if worker is None:
        raise RuntimeError(
            "Could not find 'jobscope-agent' on PATH. "
            "Is the jobscope environment loaded?"
        )
    return worker


def kill_zombie_steps(jobid: str) -> None:
    """
    Kills any lingering jobscope-agent steps for the given job ID.
    """
    try:
        # Find steps running jobscope-agent
        # Format: step_id command
        cmd = ["squeue", "--job", str(jobid), "--steps", "--noheader", "--format=%i %o"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    step_id, command = parts
                    if "jobscope-agent" in command:
                        print(f"Found zombie agent step {step_id}. Cancelling...")
                        subprocess.run(["scancel", step_id], check=False)
    except Exception as e:
        print(f"Error checking/killing zombie steps: {e}")


def cleanup_agents(
    agent_process: subprocess.Popen | object, jobid: str | None = None
) -> None:
    """
    Terminates the agent process (local or srun).
    For Slurm jobs, we terminate the srun process which will signal its children.
    This does NOT kill the actual Slurm job - only the monitoring agents.
    """
    if agent_process:
        print("Stopping agent...")

        # Check if it's a multiprocessing.Process (from demo mode)
        if hasattr(agent_process, "join"):
            agent_process.terminate()
            agent_process.join(timeout=3)
            if agent_process.is_alive():
                print("Agent did not stop gracefully, force killing...")
                agent_process.kill()
                agent_process.join()
            print("Agent stopped.")
            return

        # Assume subprocess.Popen
        # Terminate the process (local agent or srun launcher)
        # For srun, this will send signals to the remote processes it spawned
        agent_process.terminate()
        try:
            agent_process.wait(timeout=3)
            print("Agent stopped.")
        except subprocess.TimeoutExpired:
            print("Agent did not stop gracefully, force killing...")
            agent_process.kill()
            agent_process.wait()
            print("Agent killed.")

    if jobid:
        kill_zombie_steps(jobid)
