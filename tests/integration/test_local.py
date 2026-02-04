import subprocess
import sys
import time
from pathlib import Path
import os
import shutil

def test_build_and_install():
    """Test that the package can be built and installed."""
    cwd = Path.cwd()
    cmd = ["uv", "pip", "install", "-e", "."]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Install failed: {result.stderr}"

    # Check if we can import it
    cmd = [sys.executable, "-c", "import jobscope; print(jobscope.__file__)"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Import failed: {result.stderr}"

def test_local_run_once(tmp_path):
    """Test running jobscope locally with --once flag."""
    output_parquet = tmp_path / "metrics.parquet"
    
    cmd = [sys.executable, "-m", "jobscope", "--once", "--parquet", str(output_parquet)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Jobscope run failed: {result.stdout} \n {result.stderr}"
    
    # Start: Verify output
    # Check if parquet file exists
    if not output_parquet.exists():
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
    assert output_parquet.exists(), "Parquet file was not created"
    
    # We can inspect the parquet content if we have pandas/pyarrow
    import pandas as pd
    df = pd.read_parquet(output_parquet)
    assert not df.empty, "Parquet file is empty"
    assert "timestamp" in df.columns
    assert "avg_cpu_usage" in df.columns
