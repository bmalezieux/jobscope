import shutil
import subprocess


def find_worker_binary() -> str:
    """
    Find the installed Rust worker executable.

    We only need this on the login/head node. The *absolute* path we get
    will be passed to srun, so the compute nodes don't need Python.
    """
    worker = shutil.which("jobscope-agent")
    if worker is None:
        raise RuntimeError(
            "Could not find 'jobscope-agent' on PATH. "
            "Is the jobscope environment loaded?"
        )
    return worker

def cleanup_agents(agent_process: subprocess.Popen) -> None:
    """
    Terminates the agent process (local or srun).
    """
    if agent_process:
        print("Stopping agent...")
        # Send SIGTERM
        agent_process.terminate()
        try:
            agent_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print("Agent did not stop, killing...")
            agent_process.kill()
            agent_process.wait()