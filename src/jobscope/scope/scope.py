from pathlib import Path

from .tui import JobScopeApp


def start_monitoring(output_dir: str, period: float = 2.0) -> None:
    """Start the monitoring TUI."""
    app = JobScopeApp(Path(output_dir), refresh_period=period)
    app.run()
