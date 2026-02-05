from pathlib import Path

from .demo_worker import run_demo_worker
from .local_worker import run_local_worker
from .slurm_worker import run_slurm_worker


def run_agent(
    output_dir: Path,
    period: float,
    jobid: str | None = None,
    once: bool = False,
    demo: bool = False,
    demo_nodes: int = 1,
    demo_cpus: int = 4,
    demo_gpus: int = 1,
):
    if demo:
        return run_demo_worker(output_dir, period, demo_nodes, demo_cpus, demo_gpus)
    elif jobid is None:
        return run_local_worker(output_dir, period, once)
    else:
        return run_slurm_worker(output_dir, period, jobid)
