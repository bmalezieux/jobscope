from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, ProgressBar, Static

from .get_data import Snapshot, get_latest_snapshots_by_node

LOW_COLOR = "#D1F2EB"
MED_COLOR = "#48C9B0"
HIGH_COLOR = "#117A65"


def usage_color(value: float) -> str:
    """Return a palette color for a usage percentage."""
    if value < 30:
        return LOW_COLOR
    if value < 80:
        return MED_COLOR
    return HIGH_COLOR


def make_usage_legend() -> Text:
    """Create a compact usage legend for low/medium/high."""
    text = Text("Usage: ", style="bold")
    text.append("■", style=LOW_COLOR)
    text.append(" <30%  ")
    text.append("■", style=MED_COLOR)
    text.append(" 30-80%  ")
    text.append("■", style=HIGH_COLOR)
    text.append(" >80%")
    return text


def apply_progress_color(bar: ProgressBar, color: str) -> None:
    """Apply a color to a ProgressBar in a version-tolerant way."""
    if hasattr(bar, "bar_style"):
        bar.bar_style = color
    if hasattr(bar, "complete_style"):
        bar.complete_style = color
    if hasattr(bar, "percentage_style"):
        bar.percentage_style = color
    bar.styles.color = color


class NodeView(Screen):
    """Screen to view details of a single node."""

    BINDINGS = [("escape", "app.pop_screen", "Back to Cluster")]

    CSS = """
    #node_scroll {
        height: 1fr;
    }
    #resources_grid {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    .resource-col {
        width: 1fr;
        height: auto;
        padding: 1;
        margin: 0 1; 
    }
    .section-title {
        text-align: center;
        background: $accent;
        color: $text;
        width: 100%;
        margin-bottom: 1;
    }
    .legend {
        margin: 0 1 1 1;
    }
    .stat-label {
        margin-top: 1;
        color: $text-muted;
    }
    .gpu-box {
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid $primary 30%;
    }
    #proc_container {
        layout: horizontal;
        height: auto;
    }
    .proc-col {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    DataTable {
        height: auto;
    }
    """

    def __init__(self, hostname: str, snapshot: Snapshot):
        super().__init__()
        self.hostname = hostname
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield Header()

        with VerticalScroll(id="node_scroll"):
            yield Label(
                f"Node: {self.hostname} | {datetime.fromtimestamp(self.snapshot.timestamp)}",
                classes="section-title",
                id="node_header",
            )
            yield Static(make_usage_legend(), classes="legend")

            with Container(id="resources_grid"):
                with Vertical(id="cpu_mem_col", classes="resource-col"):
                    yield Label("CPU & RAM", classes="section-title")

                    yield Label("CPU Usage", classes="stat-label")
                    yield ProgressBar(
                        total=100,
                        show_eta=False,
                        show_percentage=True,
                        id="cpu_avg_bar",
                    )
                    yield Static(id="cpu_cores_visual")

                    yield Label("RAM Usage", classes="stat-label")
                    yield Label("", id="mem_text")
                    yield ProgressBar(
                        total=self.snapshot.cpus_snapshot.memory.total_gb,
                        show_eta=False,
                        show_percentage=True,
                        id="mem_bar",
                    )

                with Vertical(id="gpu_col", classes="resource-col"):
                    yield Label("GPUs", classes="section-title")

                    if not self.snapshot.gpus_snapshot.gpus:
                        yield Label("No GPUs detected", style="italic text-muted")
                    else:
                        with Vertical(id="gpu_container", classes="scroll-y"):
                            yield Static(id="gpu_list")

            with Container(id="proc_container"):
                with Vertical(classes="proc-col"):
                    yield Label("Top CPU Processes", classes="section-title")
                    yield DataTable(id="cpu_proc_table")

                with Vertical(classes="proc-col"):
                    yield Label("Top GPU Processes", classes="section-title")
                    yield DataTable(id="gpu_proc_table")

        yield Footer()

    def on_mount(self) -> None:
        cpu_table = self.query_one("#cpu_proc_table", DataTable)
        cpu_table.add_columns("PID", "Name", "CPU %", "RAM (MB)")
        cpu_table.cursor_type = "row"
        cpu_table.zebra_stripes = True

        gpu_table = self.query_one("#gpu_proc_table", DataTable)
        gpu_table.add_columns("PID", "Name", "GPU %", "VRAM (MB)", "Device")
        gpu_table.cursor_type = "row"
        gpu_table.zebra_stripes = True

        self.update_view()

    def update_snapshot(self, snapshot: Snapshot):
        self.snapshot = snapshot
        if self.is_mounted:
            self.update_view()

    def update_view(self):
        if not self.is_mounted:
            return
        snap = self.snapshot

        self.query_one("#node_header", Label).update(
            f"Node: {self.hostname} | {datetime.fromtimestamp(snap.timestamp)}"
        )

        cpu_avg = snap.cpus_snapshot.average_cpu_usage
        cpu_color = usage_color(cpu_avg)
        cpu_bar = self.query_one("#cpu_avg_bar", ProgressBar)
        cpu_bar.progress = cpu_avg
        apply_progress_color(cpu_bar, cpu_color)

        self.query_one("#cpu_cores_visual", Static).update(
            make_cpu_squares(snap.cpus_snapshot.cpus, width=20)
        )

        mem = snap.cpus_snapshot.memory
        mem_pct = (mem.used_gb / mem.total_gb * 100) if mem.total_gb > 0 else 0
        mem_color = usage_color(mem_pct)
        self.query_one("#mem_text", Label).update(
            Text(f"{mem.used_gb:.1f} / {mem.total_gb:.1f} GB", style=mem_color)
        )
        mem_bar = self.query_one("#mem_bar", ProgressBar)
        mem_bar.update(total=mem.total_gb, progress=mem.used_gb)
        apply_progress_color(mem_bar, mem_color)

        if snap.gpus_snapshot.gpus:
            gpu_text = make_gpu_details_text(snap.gpus_snapshot.gpus)
            self.query_one("#gpu_list", Static).update(gpu_text)

        self.update_proc_tables()
        self.adjust_resource_heights()

    def update_proc_tables(self):
        cpu_table = self.query_one("#cpu_proc_table", DataTable)
        cpu_table.clear()

        procs = self.snapshot.processes_snapshot.processes

        cpu_procs = sorted(procs, key=lambda p: p.cpu_usage_percent, reverse=True)
        for p in cpu_procs[:15]:
            cpu_table.add_row(
                str(p.pid),
                p.name or "?",
                f"{p.cpu_usage_percent:.1f}",
                f"{p.cpu_memory_mb:.0f}",
            )

        gpu_table = self.query_one("#gpu_proc_table", DataTable)
        gpu_table.clear()

        gpu_procs = [
            p for p in procs if p.gpu_usage_percent > 0 or p.gpu_memory_bytes > 0
        ]
        gpu_procs.sort(key=lambda p: p.gpu_usage_percent, reverse=True)

        for p in gpu_procs[:15]:
            devices = []
            if p.gpus_indexes:
                for idx in p.gpus_indexes:
                    gpu_name = f"GPU {idx}"
                    for g in self.snapshot.gpus_snapshot.gpus:
                        if g.index == idx:
                            short_name = (
                                g.name.replace("NVIDIA ", "").replace("GeForce ", "")
                                if g.name
                                else str(idx)
                            )
                            gpu_name = f"{short_name} ({idx})"
                            break
                    devices.append(gpu_name)

            device_str = ", ".join(devices) if devices else "-"

            gpu_table.add_row(
                str(p.pid),
                p.name or "?",
                f"{p.gpu_usage_percent:.1f}",
                f"{p.gpu_memory_mb:.0f}",
                device_str,
            )

    def adjust_resource_heights(self) -> None:
        """Keep CPU/RAM and GPU panes sized to their content instead of filling the screen."""
        resources_grid = self.query_one("#resources_grid")
        cpu_col = self.query_one("#cpu_mem_col")
        gpu_col = self.query_one("#gpu_col")

        cpu_height = self._calc_cpu_col_height(width=20)
        gpu_height = self._calc_gpu_col_height()

        target_height = max(cpu_height, gpu_height) + 1

        resources_grid.styles.height = target_height
        cpu_col.styles.height = target_height
        gpu_col.styles.height = target_height

    def _calc_cpu_col_height(self, width: int) -> int:
        cpu_count = len(self.snapshot.cpus_snapshot.cpus)
        cpu_lines = max(1, (cpu_count + width - 1) // width)

        fixed_lines = 7
        margin_lines = 1 + 3 + 2

        return fixed_lines + cpu_lines + margin_lines

    def _calc_gpu_col_height(self) -> int:
        gpus = self.snapshot.gpus_snapshot.gpus
        if not gpus:
            content_lines = 1
        else:
            gpu_count = len(gpus)
            content_lines = (2 * gpu_count) + (gpu_count - 1)

        return 1 + content_lines + 1 + 2


def make_gpu_details_text(gpus: list) -> Text:
    """Create concise GPU details for NodeView."""
    text = Text()
    for i, gpu in enumerate(gpus):
        if i > 0:
            text.append("\n\n")

        name = gpu.name or f"GPU {gpu.index}"

        text.append(f"{name} (#{gpu.index})", style="bold underline")
        text.append("\n")

        usage = gpu.usage_percent
        u_bar = "█" * int(usage / 10) + "░" * (10 - int(usage / 10))
        u_color = usage_color(usage)

        mem_used = gpu.memory_load.used_gb
        mem_total = gpu.memory_load.total_gb
        mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0
        m_bar = "█" * int(mem_pct / 10) + "░" * (10 - int(mem_pct / 10))
        m_color = usage_color(mem_pct)

        text.append("Usg: ", style="bold")
        text.append(f"{u_bar} {usage:>3.0f}%", style=u_color)
        text.append("   ")
        text.append("Mem: ", style="bold")
        text.append(f"{m_bar} {mem_pct:>3.0f}%", style=m_color)
        text.append(f" ({mem_used:.0f}G)", style="dim")

    return text


def make_cpu_squares(cpus: list, width: int = 20) -> Text:
    """Create a row of squares representing CPU cores."""
    text = Text()
    count = 0
    for cpu in cpus:
        usage = cpu.usage_percent
        text.append("■ ", style=usage_color(usage))
        count += 1
        if count >= width:
            text.append("\n")
            count = 0
    return text


def make_gpu_summary(gpus: list) -> Text:
    """Create a clean summary for GPUs (ClusterView)."""
    text = Text()
    for i, gpu in enumerate(gpus):
        if i > 0 and i % 2 == 0:
            text.append("\n")
        elif i > 0:
            text.append("  ")

        usage = gpu.usage_percent
        u_color = usage_color(usage)

        mem_pct = (
            (gpu.memory_load.used_gb / gpu.memory_load.total_gb) * 100
            if gpu.memory_load.total_gb > 0
            else 0
        )
        m_color = usage_color(mem_pct)

        text.append(f"#{gpu.index}: (", style="bold")
        text.append(f"{usage:>3.0f}%", style=u_color)
        text.append(" | ", style="white")
        text.append(f"{mem_pct:>3.0f}%", style=m_color)
        text.append(")", style="bold")

    return text


class ClusterView(Screen):
    """Screen to view the list of nodes in the cluster."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(make_usage_legend(), classes="legend")
        yield Label("Waiting for data...", id="empty_label")
        yield DataTable(id="cluster_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.focus()
        table.add_columns("Node", "CPUs", "RAM", "GPUs (Util | Mem)", "Last update")

    def update_data(self, snapshots: dict[str, Snapshot]):
        table = self.query_one(DataTable)
        label = self.query_one("#empty_label", Label)

        if not snapshots:
            label.display = True
            return

        label.display = False
        current_keys = set(table.rows.keys())

        for hostname, snap in snapshots.items():
            cpu_visual = make_cpu_squares(snap.cpus_snapshot.cpus, width=20)

            mem = snap.cpus_snapshot.memory
            mem_str = f"{mem.used_gb:.1f}/{mem.total_gb:.1f}G"

            if snap.gpus_snapshot.gpus:
                gpu_visual = make_gpu_summary(snap.gpus_snapshot.gpus)
                gpu_count = len(snap.gpus_snapshot.gpus)
                lines_needed = (gpu_count + 1) // 2
                cpu_count = len(snap.cpus_snapshot.cpus)
                cpu_lines = (cpu_count + 19) // 20

                row_height = max(lines_needed, cpu_lines, 1)
            else:
                gpu_visual = Text("-")
                row_height = 1

            last_update = datetime.fromtimestamp(snap.timestamp).strftime("%H:%M:%S")

            if hostname in current_keys:
                try:
                    table.update_cell(hostname, "CPUs", cpu_visual)
                    table.update_cell(hostname, "RAM", mem_str)
                    table.update_cell(hostname, "GPUs (Util | Mem)", gpu_visual)
                    table.update_cell(hostname, "Last update", last_update)
                except Exception:
                    pass
            else:
                table.add_row(
                    hostname,
                    cpu_visual,
                    mem_str,
                    gpu_visual,
                    last_update,
                    key=hostname,
                    height=row_height,
                )

        for key in list(current_keys):
            if key not in snapshots:
                table.remove_row(key)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        hostname = event.row_key.value
        app = self.app
        if isinstance(app, JobScopeApp):
            snap = app.snapshots.get(hostname)
            if snap:
                app.push_screen(NodeView(hostname, snap))


class JobScopeApp(App):
    """JobScope Terminal User Interface."""

    CSS = """
    Screen {
        layers: base overlay;
    }

    .legend {
        margin: 0 1 1 1;
    }
    
    DataTable {
        height: 1fr;
        border: solid $secondary;
    }
    
    DataTable > .datatable--cursor {
        background: $surface;
        color: auto;
        text-style: bold;
        border-left: wide $primary;
    }

    #proc_container {
        height: 1fr;
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    .proc-col {
        height: 100%;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, output_dir: Path, refresh_period: float = 1.0):
        super().__init__()
        self.output_dir = output_dir
        self.refresh_period = max(0.2, float(refresh_period))
        self.snapshots: dict[str, Snapshot] = {}
        self._quitting = False

    def on_mount(self) -> None:
        self.push_screen(ClusterView())
        self.set_interval(self.refresh_period, self.refresh_data)

    def action_quit(self) -> None:
        self._quitting = True
        self.exit()

    def refresh_data(self) -> None:
        if self._quitting:
            return
        self.snapshots = get_latest_snapshots_by_node(self.output_dir)

        if isinstance(self.screen, ClusterView):
            self.screen.update_data(self.snapshots)

        if isinstance(self.screen, NodeView):
            hostname = self.screen.hostname
            if hostname in self.snapshots:
                self.screen.update_snapshot(self.snapshots[hostname])


if __name__ == "__main__":
    app = JobScopeApp(Path("./snapshots"))
    app.run()
