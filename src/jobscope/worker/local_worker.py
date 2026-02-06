import subprocess
import sys
import time
from pathlib import Path

from ..logging import get_logger
from .utils import find_worker_binary

logger = get_logger(__name__)


def run_local_worker(output_dir: Path, period: float, once: bool = False):
    try:
        agent_path = find_worker_binary()
        logger.info("Starting worker: %s", agent_path)

        cmd = [
            agent_path,
            "--output",
            str(output_dir),
            "--period",
            str(period),
            "--mode",
            "local",
        ]

        if not once:
            cmd.append("--continuous")

        # Start worker in background
        worker_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        logger.info("Worker started with PID %s", worker_process.pid)

        # Give it a moment to start
        time.sleep(0.5)

        if worker_process.poll() is not None:
            # If in once mode and exited successfully, that's fine
            if once and worker_process.returncode == 0:
                logger.info("Worker completed successfully (once mode)")
            else:
                logger.error("Worker failed to start immediately.")
                if worker_process.stderr:
                    logger.error(worker_process.stderr.read().decode())
                sys.exit(1)

    except Exception as e:
        logger.error("Failed to start worker: %s", e)
        sys.exit(1)

    return worker_process
