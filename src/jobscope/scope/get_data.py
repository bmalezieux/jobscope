import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class MemoryLoad(BaseModel):
    """Memory usage information."""

    used_bytes: int
    total_bytes: int

    @property
    def used_gb(self) -> float:
        """Memory used in GB."""
        return self.used_bytes / (1024**3)

    @property
    def total_gb(self) -> float:
        """Total memory in GB."""
        return self.total_bytes / (1024**3)

    @property
    def usage_percent(self) -> float:
        """Memory usage percentage."""
        if self.total_bytes == 0:
            return 0.0
        return (self.used_bytes / self.total_bytes) * 100


class CPUInfo(BaseModel):
    """CPU core information."""

    index: int
    name: Optional[str] = None
    usage_percent: float


class GPUInfo(BaseModel):
    """GPU device information."""

    index: int
    name: Optional[str] = None
    usage_percent: float
    memory_load: MemoryLoad


class ProcessInfo(BaseModel):
    """Process resource usage information."""

    pid: int
    name: Optional[str] = None
    cpu_usage_percent: float
    cpu_memory_bytes: int
    gpu_usage_percent: float
    gpu_memory_bytes: int
    cpus_indexes: List[int] = Field(default_factory=list)
    gpus_indexes: List[int] = Field(default_factory=list)

    @property
    def cpu_memory_mb(self) -> float:
        """CPU memory in MB."""
        return self.cpu_memory_bytes / (1024**2)

    @property
    def gpu_memory_mb(self) -> float:
        """GPU memory in MB."""
        return self.gpu_memory_bytes / (1024**2)


class CPUsSnapshot(BaseModel):
    """Snapshot of all CPU cores and system memory."""

    cpus: List[CPUInfo]
    memory: MemoryLoad

    @property
    def average_cpu_usage(self) -> float:
        """Average CPU usage across all cores."""
        if not self.cpus:
            return 0.0
        return sum(cpu.usage_percent for cpu in self.cpus) / len(self.cpus)


class GPUsSnapshot(BaseModel):
    """Snapshot of all GPU devices."""

    gpus: List[GPUInfo]


class ProcessesSnapshot(BaseModel):
    """Snapshot of all monitored processes."""

    processes: List[ProcessInfo]

    def top_cpu_processes(self, n: int = 5) -> List[ProcessInfo]:
        """Get top N processes by CPU usage."""
        return sorted(self.processes, key=lambda p: p.cpu_usage_percent, reverse=True)[
            :n
        ]

    def top_gpu_processes(self, n: int = 5) -> List[ProcessInfo]:
        """Get top N processes by GPU usage."""
        return sorted(self.processes, key=lambda p: p.gpu_usage_percent, reverse=True)[
            :n
        ]


class Snapshot(BaseModel):
    """Complete system snapshot."""

    timestamp: int
    cpus_snapshot: CPUsSnapshot
    gpus_snapshot: GPUsSnapshot
    processes_snapshot: ProcessesSnapshot


def parse_snapshot(json_path: Path) -> Snapshot:
    """
    Parse a snapshot JSON file into structured data.

    Args:
        json_path: Path to the JSON snapshot file

    Returns:
        Parsed Snapshot object

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file is not valid JSON
        pydantic.ValidationError: If the data doesn't match the expected schema
    """
    with open(json_path, "r") as f:
        data = json.load(f)
    return Snapshot(**data)


def get_latest_snapshots_by_node(output_dir: Path) -> dict[str, Snapshot]:
    """
    Get the most recent snapshot for each node from the output directory.

    Args:
        output_dir: Directory containing snapshot JSON files

    Returns:
        Dictionary mapping hostname to latest Snapshot object
    """
    latest_files: dict[str, tuple[int, Path]] = {}

    # Pattern: snapshot_{hostname}_{timestamp}.json
    # Or legacy: snapshot_{timestamp}.json (treat as "unknown")
    for file_path in output_dir.glob("snapshot_*.json"):
        try:
            parts = file_path.stem.split("_")
            if len(parts) >= 3:
                hostname = "_".join(parts[1:-1])
                timestamp = int(parts[-1])
            elif len(parts) == 2:
                hostname = "unknown"
                timestamp = int(parts[-1])
            else:
                continue
        except ValueError:
            continue

        current = latest_files.get(hostname)
        if current is None or timestamp > current[0]:
            latest_files[hostname] = (timestamp, file_path)

    snapshots: dict[str, Snapshot] = {}
    for hostname, (_ts, file_path) in latest_files.items():
        try:
            snapshots[hostname] = parse_snapshot(file_path)
        except Exception:
            continue

    return snapshots
