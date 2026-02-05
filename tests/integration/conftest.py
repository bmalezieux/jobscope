import multiprocessing
import shutil
import subprocess
from pathlib import Path

import pytest

INTEGRATION_DIR = Path(__file__).parent
WORKSPACE_DIR = INTEGRATION_DIR.parent.parent
ARTIFACTS_DIR = INTEGRATION_DIR / ".artifacts"

SLURM_CTL_CONTAINER = "slurm-docker-cluster-slurmctld"


def _run(cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)


@pytest.fixture(scope="session")
def artifacts_dir() -> Path:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    return ARTIFACTS_DIR


@pytest.fixture(scope="session")
def slurm_cluster(artifacts_dir: Path):
    if shutil.which("docker") is None:
        pytest.skip("Docker is not available. Install Docker to run Slurm integration tests.")

    res = _run(
        "docker ps --filter name=slurm-docker-cluster-slurmctld --format '{{.Status}}'",
        check=False,
    )
    if "Up" not in res.stdout:
        pytest.skip(
            "Slurm cluster not running.\n"
            "Start it with:\n"
            "  tests/integration/scripts/cluster.sh start\n"
            "Then run:\n"
            "  uv run pytest -m slurm\n"
        )

    if _run(f"docker exec {SLURM_CTL_CONTAINER} scontrol ping", check=False).returncode != 0:
        pytest.skip(
            "Slurm controller not ready yet.\n"
            "Wait a moment or rerun:\n"
            "  tests/integration/scripts/cluster.sh start"
        )

    venv_check = _run(
        f"docker exec {SLURM_CTL_CONTAINER} test -x /root/jobscope-venv/bin/python",
        check=False,
    )
    if venv_check.returncode != 0:
        pytest.skip(
            "jobscope is not installed in the slurmctld container.\n"
            "Install it with:\n"
            "  tests/integration/scripts/cluster.sh install"
        )

    agent_path = WORKSPACE_DIR / "jobscope-agent" / "target" / "release" / "jobscope-agent"
    if not agent_path.exists():
        pytest.skip(
            "jobscope-agent is not built on the host.\n"
            "Build it with:\n"
            "  tests/integration/scripts/cluster.sh start"
        )

    cpu_count = multiprocessing.cpu_count()
    if cpu_count < 2:
        pytest.skip(
            f"Ideally we need at least 2 CPUs for testing, found {cpu_count}. "
            "Skipping integration tests that require multiple CPUs."
        )

    yield
