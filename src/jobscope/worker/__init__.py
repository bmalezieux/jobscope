from pathlib import Path

from .local_worker import run_local_worker
from .slurm_worker import run_slurm_worker


def run_agent(output_dir: Path, period: float, jobid: int | None = None):
    if jobid is None:
        run_local_worker(output_dir, period)
    else:
        run_slurm_worker(output_dir, period, jobid)