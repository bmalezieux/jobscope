from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Header, Footer, DataTable, Static, Label, ProgressBar
from textual.screen import Screen

from .get_data import Snapshot, get_latest_snapshots_by_node
from pathlib import Path
from datetime import datetime
from rich.text import Text

# Usage color palette
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
            yield Label(f"Node: {self.hostname} | {datetime.fromtimestamp(self.snapshot.timestamp)}", classes="section-title", id="node_header")
            yield Static(make_usage_legend(), classes="legend")
            
            with Container(id="resources_grid"):
                # LEFT: CPU & RAM
                with Vertical(id="cpu_mem_col", classes="resource-col"):
                    yield Label("CPU & RAM", classes="section-title")
                    
                    # Processor Info
                    yield Label("CPU Usage", classes="stat-label")
                    yield ProgressBar(total=100, show_eta=False, show_percentage=True, id="cpu_avg_bar")                    
                    yield Static(id="cpu_cores_visual")

                    # Memory Info
                    yield Label(f"RAM Usage", classes="stat-label")
                    yield Label("", id="mem_text")
                    yield ProgressBar(total=self.snapshot.cpus_snapshot.memory.total_gb, show_eta=False, show_percentage=True, id="mem_bar")

                # RIGHT: GPU
                with Vertical(id="gpu_col", classes="resource-col"):
                    yield Label("GPUs", classes="section-title")
                    
                    if not self.snapshot.gpus_snapshot.gpus:
                         yield Label("No GPUs detected", style="italic text-muted")
                    else:
                        with Vertical(id="gpu_container", classes="scroll-y"):
                            yield Static(id="gpu_list")

            # Processes
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
        
        # --- Update Header ---
        self.query_one("#node_header", Label).update(f"Node: {self.hostname} | {datetime.fromtimestamp(snap.timestamp)}")

        # --- Update CPU & RAM ---
        cpu_avg = snap.cpus_snapshot.average_cpu_usage
        cpu_color = usage_color(cpu_avg)
        cpu_bar = self.query_one("#cpu_avg_bar", ProgressBar)
        cpu_bar.progress = cpu_avg
        apply_progress_color(cpu_bar, cpu_color)
        
        # Cores Visual
        self.query_one("#cpu_cores_visual", Static).update(make_cpu_squares(snap.cpus_snapshot.cpus, width=20))
        
        # RAM
        mem = snap.cpus_snapshot.memory
        mem_pct = (mem.used_gb / mem.total_gb * 100) if mem.total_gb > 0 else 0
        mem_color = usage_color(mem_pct)
        self.query_one("#mem_text", Label).update(
            Text(f"{mem.used_gb:.1f} / {mem.total_gb:.1f} GB", style=mem_color)
        )
        mem_bar = self.query_one("#mem_bar", ProgressBar)
        mem_bar.update(total=mem.total_gb, progress=mem.used_gb)
        apply_progress_color(mem_bar, mem_color)

        # --- Update GPUs ---
        if snap.gpus_snapshot.gpus:
             gpu_text = make_gpu_details_text(snap.gpus_snapshot.gpus)
             self.query_one("#gpu_list", Static).update(gpu_text)

        # --- Update Tables ---
        self.update_proc_tables()
        self.adjust_resource_heights()
        
    def update_proc_tables(self):
        # CPU Table
        cpu_table = self.query_one("#cpu_proc_table", DataTable)
        cpu_table.clear()
        
        procs = self.snapshot.processes_snapshot.processes
        
        # Top CPU
        cpu_procs = sorted(procs, key=lambda p: p.cpu_usage_percent, reverse=True)
        for p in cpu_procs[:15]:
            cpu_table.add_row(
                str(p.pid),
                p.name or "?",
                f"{p.cpu_usage_percent:.1f}",
                f"{p.cpu_memory_mb:.0f}"
            )
            
        # GPU Table
        gpu_table = self.query_one("#gpu_proc_table", DataTable)
        gpu_table.clear()
        
        # Filter for GPU usage
        gpu_procs = [p for p in procs if p.gpu_usage_percent > 0 or p.gpu_memory_bytes > 0]
        gpu_procs.sort(key=lambda p: p.gpu_usage_percent, reverse=True)
        
        for p in gpu_procs[:15]:
            devices = []
            if p.gpus_indexes:
                for idx in p.gpus_indexes:
                    gpu_name = f"GPU {idx}"
                    # Try to match index to name in snapshot
                    for g in self.snapshot.gpus_snapshot.gpus:
                        if g.index == idx:
                            short_name = g.name.replace("NVIDIA ", "").replace("GeForce ", "") if g.name else str(idx)
                            gpu_name = f"{short_name} ({idx})"
                            break
                    devices.append(gpu_name)
            
            device_str = ", ".join(devices) if devices else "-"
            
            gpu_table.add_row(
                str(p.pid),
                p.name or "?",
                f"{p.gpu_usage_percent:.1f}",
                f"{p.gpu_memory_mb:.0f}",
                device_str
            )

    def adjust_resource_heights(self) -> None:
        """Keep CPU/RAM and GPU panes sized to their content instead of filling the screen."""
        resources_grid = self.query_one("#resources_grid")
        cpu_col = self.query_one("#cpu_mem_col")
        gpu_col = self.query_one("#gpu_col")

        cpu_height = self._calc_cpu_col_height(width=20)
        gpu_height = self._calc_gpu_col_height()

        # Add a small buffer to avoid clipping from margins/padding.
        target_height = max(cpu_height, gpu_height) + 1

        resources_grid.styles.height = target_height
        cpu_col.styles.height = target_height
        gpu_col.styles.height = target_height

    def _calc_cpu_col_height(self, width: int) -> int:
        cpu_count = len(self.snapshot.cpus_snapshot.cpus)
        cpu_lines = max(1, (cpu_count + width - 1) // width)

        # Fixed lines: title + avg label + bar + cores label + ram label + mem text + mem bar
        fixed_lines = 7
        # Margins/padding: section-title bottom margin + stat-label top margins (3) + column padding (top+bottom)
        margin_lines = 1 + 3 + 2

        return fixed_lines + cpu_lines + margin_lines

    def _calc_gpu_col_height(self) -> int:
        gpus = self.snapshot.gpus_snapshot.gpus
        if not gpus:
            content_lines = 1
        else:
            gpu_count = len(gpus)
            # 2 lines per GPU + 1 blank line between GPUs
            content_lines = (2 * gpu_count) + (gpu_count - 1)

        # Title line + title margin + column padding (top+bottom)
        return 1 + content_lines + 1 + 2

def make_gpu_details_text(gpus: list) -> Text:
    """Create concise GPU details for NodeView."""
    text = Text()
    for i, gpu in enumerate(gpus):
        if i > 0:
            text.append("\n\n")
        
        name = gpu.name or f"GPU {gpu.index}"
        
        # Split logic: Name on line 1, Bars on line 2
        text.append(f"{name} (#{gpu.index})", style="bold underline")
        text.append("\n")
        
        # Usage
        usage = gpu.usage_percent
        # Reduce bar width to 10
        u_bar = "█" * int(usage / 10) + "░" * (10 - int(usage / 10))
        u_color = usage_color(usage)
        
        # Memory
        mem_used = gpu.memory_load.used_gb
        mem_total = gpu.memory_load.total_gb
        mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0
        m_bar = "█" * int(mem_pct / 10) + "░" * (10 - int(mem_pct / 10))
        m_color = usage_color(mem_pct)
        
        # Line 2: Usg: [|||||.....] 100%   Mem: [|||||.....] 100% (32.0G)
        text.append(f"Usg: ", style="bold")
        text.append(f"{u_bar} {usage:>3.0f}%", style=u_color)
        text.append("   ")
        text.append(f"Mem: ", style="bold")
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
        # 2 GPUs per row
        if i > 0 and i % 2 == 0:
            text.append("\n")
        elif i > 0:
             text.append("  ")
        
        # Usage Color (High = Green)
        usage = gpu.usage_percent
        u_color = usage_color(usage)
        
        # Mem Color (High = Green)
        mem_pct = (gpu.memory_load.used_gb / gpu.memory_load.total_gb) * 100 if gpu.memory_load.total_gb > 0 else 0
        m_color = usage_color(mem_pct)

        # Format: #0: (50% | 40%)
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
        # table.row_height = 2  <-- Removed fixed row height, using dynamic row height calculation
        table.focus()
        # Node, CPUs (visual), RAM (text+bar), GPUs (Util | Mem), Last Update
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
            # CPUs
            cpu_visual = make_cpu_squares(snap.cpus_snapshot.cpus, width=20) # Adjusted width
            
            # RAM
            mem = snap.cpus_snapshot.memory
            mem_str = f"{mem.used_gb:.1f}/{mem.total_gb:.1f}G"

            # GPUs
            if snap.gpus_snapshot.gpus:
                gpu_visual = make_gpu_summary(snap.gpus_snapshot.gpus)
                # Calculate needed height: 1 line per 2 GPUs (approx)
                # Actually, make_gpu_summary adds newlines.
                # Rich text rendered in DataTable cell might require height adjusting if rows are fixed.
                # However, Textual DataTable with height=None (default) on add_row might not auto-expand dynamically 
                # if row_height is set on the table.
                # But we can override height for specific rows if needed, or rely on max height.
                # Let's count lines.
                gpu_count = len(snap.gpus_snapshot.gpus)
                lines_needed = (gpu_count + 1) // 2 
                cpu_count = len(snap.cpus_snapshot.cpus)
                cpu_lines = (cpu_count + 19) // 20 # width=20
                
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
                    # Note: Cannot update row height easily here. 
                    # If hardware changes significantly (unlikely), row might look clipped.
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
                    height=row_height 
                )
                
        # Remove old nodes
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
    
    /* Cluster View Styles */
    DataTable {
        height: 1fr;
        border: solid $secondary;
    }
    
    /* Mix blend mode or just simple background change to keep colors visible */
    DataTable > .datatable--cursor {
        background: $surface;
        color: auto;
        text-style: bold;
        border-left: wide $primary;
    }

    /* Node View Styles */
    #proc_container {
        height: 1fr;
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    .proc-col {
        height: 100%;
        /* border: solid $secondary; */
        padding: 0 1;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, output_dir: Path):
        super().__init__()
        self.output_dir = output_dir
        self.snapshots: dict[str, Snapshot] = {}
        self._quitting = False

    def on_mount(self) -> None:
        self.push_screen(ClusterView())
        self.set_interval(1.0, self.refresh_data)

    def action_quit(self) -> None:
        self._quitting = True
        self.exit()

    def refresh_data(self) -> None:
        if self._quitting:
            return
        self.snapshots = get_latest_snapshots_by_node(self.output_dir)
        
        # Update ClusterView
        if isinstance(self.screen, ClusterView):
            self.screen.update_data(self.snapshots)
            
        # Update NodeView if active
        if isinstance(self.screen, NodeView):
            hostname = self.screen.hostname
            # If the current node isn't in snapshots anymore (rare), keep showing old data or handle
            if hostname in self.snapshots:
                self.screen.update_snapshot(self.snapshots[hostname])

if __name__ == "__main__":
    app = JobScopeApp(Path("./snapshots"))
    app.run()
