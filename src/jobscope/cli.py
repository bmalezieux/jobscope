import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from jobscope.scope import start_monitoring
from jobscope.worker import run_agent

import signal

def main() -> None:
    """Main entry point for the jobscope CLI."""
    parser = argparse.ArgumentParser(
        prog="jobscope",
        description="Monitor system resources (CPU, GPU, processes) on compute nodes"
    )

    parser.add_argument(
        "-p", "--period",
        type=float,
        default=2.0,
        help="Refresh period in seconds (default: 2.0)"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no continuous monitoring)"
    )

    parser.add_argument(
        "--parquet",
        help="Output path for a Parquet file containing all collected data (e.g. ./data.parquet)"
    )

    parser.add_argument(
        "--jobid",
        type=int,
        required=False,
        help="Slurm job ID to monitor (default: local)"
    )
    
    args = parser.parse_args()

    temp_dir = TemporaryDirectory(prefix="jobscope_snapshots_")
    output_dir = Path(temp_dir.name)
    print(f"Using temporary directory: {output_dir}")

    # Spawn agent
    agent_process = run_agent(output_dir, args.period, args.jobid)    

    # Handle signals to ensure cleanup runs
    def signal_handler(sig, frame):
        raise KeyboardInterrupt
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start the monitoring scope (TUI)
        start_monitoring(
            output_dir=str(output_dir),
            period=args.period,
            once=args.once
        )

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in TUI: {e}")
    finally:
        print("\nCleaning up...")
        
        from .worker.utils import cleanup_agents
        if agent_process:
            cleanup_agents(agent_process)

        if args.parquet:
            print(f"Exporting data to {args.parquet}...")
            try:
                from .get_data import export_to_parquet
                export_to_parquet(output_dir, Path(args.parquet))
                print("Export complete.")
            except Exception as e:
                print(f"Failed to export parquet: {e}")
                import traceback
                traceback.print_exc()

        if temp_dir:
            print("Cleaning up temporary directory...")
            temp_dir.cleanup()
