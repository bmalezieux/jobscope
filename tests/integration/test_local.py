import subprocess
import sys


def test_build_and_install():
    """Test that the package can be built and installed."""
    cmd = ["uv", "pip", "install", "-e", "."]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Install failed: {result.stderr}"

    # Check if we can import it
    cmd = [sys.executable, "-c", "import jobscope"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Import failed: {result.stderr}"


def test_local_run_once():
    """Test running jobscope locally with --once flag."""

    cmd = [sys.executable, "-m", "jobscope", "--once"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert (
        result.returncode == 0
    ), f"Jobscope run failed: {result.stdout} \n {result.stderr}"
