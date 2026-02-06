import argparse
import logging
import shutil
import signal
from datetime import datetime
from pathlib import Path

from jobscope.logging import configure_logging
from jobscope.scope import start_monitoring
from jobscope.worker import run_worker

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the jobscope CLI."""
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="jobscope",
        description="Monitor system resources (CPU, GPU, processes) on compute nodes",
    )

    parser.add_argument(
        "-p",
        "--period",
        type=float,
        default=2.0,
        help="Refresh period in seconds (default: 2.0)",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no continuous monitoring)",
    )

    parser.add_argument(
        "--jobid",
        type=str,
        required=False,
        help="Slurm job ID to monitor (default: local)",
    )

    parser.add_argument(
        "--snapshots-dir",
        type=str,
        default=".jobscope_snapshots",
        help="Directory to store snapshot data (default: .jobscope_snapshots in current directory)",
    )

    parser.add_argument(
        "--keep-snapshots",
        action="store_true",
        help="Keep snapshot files after jobscope exits (default: cleanup)",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without TUI (useful for background logging)",
    )

    parser.add_argument(
        "--summary",
        type=str,
        default=None,
        help="Write a JSON summary of snapshots to this path when exiting",
    )

    # Demo options
    parser.add_argument(
        "--demo", action="store_true", help="Run in demo mode with simulated data"
    )
    parser.add_argument(
        "--demo-nodes",
        type=int,
        default=4,
        help="Number of nodes to simulate in demo mode",
    )
    parser.add_argument(
        "--demo-cpus", type=int, default=32, help="Number of CPUs per node in demo mode"
    )
    parser.add_argument(
        "--demo-gpus", type=int, default=4, help="Number of GPUs per node in demo mode"
    )

    args = parser.parse_args()

    # Create snapshots directory with timestamped subdirectory
    # This ensures the directory is on a shared filesystem accessible to compute nodes
    snapshots_base = Path(args.snapshots_dir)
    if not snapshots_base.is_absolute():
        snapshots_base = Path.cwd() / snapshots_base

    # Create timestamped subdirectory for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = snapshots_base / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Using snapshot directory: %s", output_dir)

    # Spawn worker
    worker_process = run_worker(
        output_dir,
        args.period,
        args.jobid,
        args.once,
        demo=args.demo,
        demo_nodes=args.demo_nodes,
        demo_cpus=args.demo_cpus,
        demo_gpus=args.demo_gpus,
    )

    # Handle signals to ensure cleanup runs
    def signal_handler(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.once:
            logger.info("Refreshed snapshots.")
            if worker_process:
                worker_process.wait()

            from .scope.get_data import get_latest_snapshots_by_node

            snapshots = get_latest_snapshots_by_node(output_dir)
            for hostname, snap in snapshots.items():
                logger.info("Node: %s", hostname)
                logger.info("  CPU: %.1f%%", snap.cpus_snapshot.average_cpu_usage)
                logger.info(
                    "  Mem: %.1f/%.1f GB",
                    snap.cpus_snapshot.memory.used_gb,
                    snap.cpus_snapshot.memory.total_gb,
                )
        elif args.headless:
            logger.info("Running in headless mode. Logs at %s", output_dir)
            logger.info("Press Ctrl+C to stop.")
            import time

            while True:
                time.sleep(1)
        else:
            # Start the monitoring scope (TUI)
            start_monitoring(output_dir=str(output_dir), period=args.period)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error("Error in TUI: %s", e)
    finally:
        logger.info("Cleaning up...")

        from .worker.utils import cleanup_workers

        if worker_process:
            cleanup_workers(worker_process, args.jobid)

        if args.summary:
            from .scope.get_data import write_snapshots_summary

            summary_path = Path(args.summary)
            if not summary_path.is_absolute():
                summary_path = Path.cwd() / summary_path

            try:
                write_snapshots_summary(output_dir, summary_path)
                logger.info("Wrote summary to: %s", summary_path)
            except Exception as e:
                logger.warning("Could not write summary: %s", e)

        # Clean up snapshot directory unless --keep-snapshots is set
        if not args.keep_snapshots:
            logger.info("Cleaning up snapshot directory...")
            try:
                shutil.rmtree(output_dir)
                logger.info("Removed %s", output_dir)
            except Exception as e:
                logger.warning("Could not remove %s: %s", output_dir, e)
        else:
            logger.info("Snapshots preserved in: %s", output_dir)
