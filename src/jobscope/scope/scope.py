from pathlib import Path

from .tui import JobScopeApp


def start_monitoring(output_dir: str, period: float = 2.0, once: bool = False):
    """
    Start the monitoring scope (TUI).
    
    Args:
        output_dir: Directory where agent snapshots will be stored
        period: Time in seconds between snapshots (default: 2.0) - Unused for TUI refresh rate for now
        once: If True, run once and exit. (Not supported in TUI yet, or could just print)
    """
    # TODO: Handle 'once' mode if needed (maybe just print latest snapshot using legacy display)
    
    app = JobScopeApp(Path(output_dir))
    app.run()
