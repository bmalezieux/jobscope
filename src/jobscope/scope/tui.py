from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, DataTable, Static, Button, Label, ProgressBar
from textual.screen import Screen
from textual.reactive import reactive
from textual.binding import Binding
from textual import work

from .get_data import Snapshot, get_latest_snapshots_by_node
from pathlib import Path
from datetime import datetime
from rich.text import Text


class NodeView(Screen):
    """Screen to view details of a single node."""

    BINDINGS = [("escape", "app.pop_screen", "Back to Cluster")]
    
    def __init__(self, hostname: str, snapshot: Snapshot):
        super().__init__()
        self.hostname = hostname
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(f"Node: {self.hostname} | {datetime.fromtimestamp(self.snapshot.timestamp)}")
        
        with Container(id="resources"):
            # CPU Section
            yield Label("[bold blue]CPU Usage[/]")
            with Horizontal(classes="resource-row"):
                yield Label(f"Avg: {self.snapshot.cpus_snapshot.average_cpu_usage:.1f}%", id="cpu_avg_label")
                pb = ProgressBar(total=100, show_eta=False, id="cpu_avg_bar")
                pb.progress = self.snapshot.cpus_snapshot.average_cpu_usage
                yield pb

            yield Label(f"Memory: {self.snapshot.cpus_snapshot.memory.used_gb:.1f}/{self.snapshot.cpus_snapshot.memory.total_gb:.1f} GB", id="mem_label")
            pb_mem = ProgressBar(total=self.snapshot.cpus_snapshot.memory.total_gb, show_eta=False, id="mem_bar")
            pb_mem.progress = self.snapshot.cpus_snapshot.memory.used_gb
            yield pb_mem

            # GPU Section
            if self.snapshot.gpus_snapshot.gpus:
                yield Label("\n[bold green]GPU Usage[/]")
                for gpu in self.snapshot.gpus_snapshot.gpus:
                    name = gpu.name or f"GPU {gpu.index}"
                    yield Label(f"{name}: {gpu.usage_percent:.1f}%", id=f"gpu_label_{gpu.index}")
                    pb_gpu = ProgressBar(total=100, show_eta=False, id=f"gpu_bar_{gpu.index}")
                    pb_gpu.progress = gpu.usage_percent
                    yield pb_gpu
                    
                    yield Label(f"VRAM: {gpu.memory_load.used_gb:.1f}/{gpu.memory_load.total_gb:.1f} GB", id=f"vram_label_{gpu.index}")
                    pb_vram = ProgressBar(total=gpu.memory_load.total_gb, show_eta=False, id=f"vram_bar_{gpu.index}")
                    pb_vram.progress = gpu.memory_load.used_gb
                    yield pb_vram

        # Processes
        with Container(id="proc_container"):
            with Vertical(classes="proc-col"):
                yield Label("[bold blue]Top CPU Processes[/]")
                yield DataTable(id="cpu_proc_table")
            
            with Vertical(classes="proc-col"):
                yield Label("[bold green]Top GPU Processes[/]")
                yield DataTable(id="gpu_proc_table")
                
        yield Footer()

    def on_mount(self) -> None:
        cpu_table = self.query_one("#cpu_proc_table", DataTable)
        cpu_table.add_columns("PID", "Name", "CPU %", "Mem (MB)")
        
        gpu_table = self.query_one("#gpu_proc_table", DataTable)
        gpu_table.add_columns("PID", "Name", "GPU %", "VRAM (MB)", "Device")
        
        self.update_table()

    def update_snapshot(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self.update_table()
        
        try:
            # Update CPU
            self.query_one("#cpu_avg_label", Label).update(f"Avg: {snapshot.cpus_snapshot.average_cpu_usage:.1f}%")
            self.query_one("#cpu_avg_bar", ProgressBar).progress = snapshot.cpus_snapshot.average_cpu_usage
            
            # Update Memory
            self.query_one("#mem_label", Label).update(f"Memory: {snapshot.cpus_snapshot.memory.used_gb:.1f}/{snapshot.cpus_snapshot.memory.total_gb:.1f} GB")
            self.query_one("#mem_bar", ProgressBar).progress = snapshot.cpus_snapshot.memory.used_gb
            
            # Update GPUs
            if snapshot.gpus_snapshot.gpus:
                for gpu in snapshot.gpus_snapshot.gpus:
                    try:
                        name = gpu.name or f"GPU {gpu.index}"
                        self.query_one(f"#gpu_label_{gpu.index}", Label).update(f"{name}: {gpu.usage_percent:.1f}%")
                        self.query_one(f"#gpu_bar_{gpu.index}", ProgressBar).progress = gpu.usage_percent
                        
                        self.query_one(f"#vram_label_{gpu.index}", Label).update(f"VRAM: {gpu.memory_load.used_gb:.1f}/{gpu.memory_load.total_gb:.1f} GB")
                        self.query_one(f"#vram_bar_{gpu.index}", ProgressBar).progress = gpu.memory_load.used_gb
                    except Exception:
                        pass
        except Exception:
            pass
        
    def update_table(self):
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
            # Map GPU indexes to names if possible
            devices = []
            if p.gpus_indexes:
                for idx in p.gpus_indexes:
                    # Try to find GPU name from snapshot
                    gpu_name = f"GPU {idx}"
                    for g in self.snapshot.gpus_snapshot.gpus:
                        if g.index == idx:
                            # Shorten name for display
                            short_name = g.name.replace("NVIDIA ", "").replace("GeForce ", "") if g.name else f"GPU {idx}"
                            gpu_name = f"{short_name} (#{idx})"
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

def make_cpu_squares(cpus: list) -> Text:
    """Create a row of squares representing CPU cores."""
    text = Text()
    for cpu in cpus:
        usage = cpu.usage_percent
        if usage < 50:
            color = "#ff6b6b"   # red
        elif usage < 80:
            color = "#ffd93d"   # yellow
        else:
            color = "#51cf66"   # green
        text.append("■", style=color)
    return text

def make_gpu_squares(gpus: list) -> Text:
    """Create a representation for GPUs."""
    text = Text()
    for i, gpu in enumerate(gpus):
        if i > 0:
            text.append("  ")
        
        # Core usage
        usage = gpu.usage_percent
        if usage < 50:
            color = "#ff6b6b"   # red
        elif usage < 80:
            color = "#ffd93d"   # yellow
        else:
            color = "#51cf66"   # green

        # Mem usage
        mem_pct = (gpu.memory_load.used_gb / gpu.memory_load.total_gb) * 100 if gpu.memory_load.total_gb > 0 else 0
        if mem_pct < 50:
            mem_color = "#51cf66"
        elif mem_pct < 80:
            mem_color = "#ffd93d"
        else:
            mem_color = "#ff6b6b"
        
        text.append(f"#{i}: ", style="bold")
        text.append(f"{usage:.0f}%", style=color)
        text.append(" | ", style="white")
        text.append(f"{mem_pct:.0f}%", style=mem_color)
        
    return text

class ClusterView(Screen):
    """Screen to view the list of nodes in the cluster."""
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Waiting for data...", id="empty_label")
        yield DataTable(id="cluster_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.focus()
        # Node, CPUs (visual), RAM (text+bar), GPUs (visual), Last Update
        table.add_columns("Node", "CPUs", "RAM", "GPUs (usage | mem)", "Last update")
        
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
            cpu_visual = make_cpu_squares(snap.cpus_snapshot.cpus)
            
            # RAM
            mem = snap.cpus_snapshot.memory
            mem_str = f"{mem.used_gb:.1f}/{mem.total_gb:.1f}G"

            # GPUs
            if snap.gpus_snapshot.gpus:
                gpu_visual = make_gpu_squares(snap.gpus_snapshot.gpus)
            else:
                gpu_visual = Text("-")

            last_update = datetime.fromtimestamp(snap.timestamp).strftime("%H:%M:%S")
            
            if hostname in current_keys:
                try:
                    table.update_cell(hostname, "CPUs", cpu_visual)
                    table.update_cell(hostname, "RAM", mem_str)
                    table.update_cell(hostname, "GPUs (usage | mem)", gpu_visual)
                    table.update_cell(hostname, "Last update", last_update)
                except Exception:
                    table.remove_row(hostname)
                    table.add_row(hostname, cpu_visual, mem_str, gpu_visual, last_update, key=hostname)
            else:
                table.add_row(hostname, cpu_visual, mem_str, gpu_visual, last_update, key=hostname)
                
        for key in current_keys:
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
        align: center middle;
    }
    DataTable {
        height: 1fr;
    }
    #resources {
        height: auto;
        border: solid blue;
        padding: 1;
    }
    .resource-row {
        height: auto;
    }
    #proc_container {
        height: 1fr;
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }
    .proc-col {
        height: 100%;
        border: solid green;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, output_dir: Path):
        super().__init__()
        self.output_dir = output_dir
        self.snapshots: dict[str, Snapshot] = {}

    def on_mount(self) -> None:
        self.push_screen(ClusterView())
        self.set_interval(1.0, self.refresh_data)

    def refresh_data(self) -> None:
        self.snapshots = get_latest_snapshots_by_node(self.output_dir)
        
        # Update ClusterView
        if isinstance(self.screen, ClusterView):
            self.screen.update_data(self.snapshots)
            
        # Update NodeView if active
        if isinstance(self.screen, NodeView):
            hostname = self.screen.hostname
            if hostname in self.snapshots:
                self.screen.update_snapshot(self.snapshots[hostname])

if __name__ == "__main__":
    app = JobScopeApp(Path("./snapshots"))
    app.run()
