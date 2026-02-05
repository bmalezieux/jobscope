import random
import time
from multiprocessing import Process
from pathlib import Path

from ..scope.get_data import (
    CPUInfo,
    CPUsSnapshot,
    GPUInfo,
    GPUsSnapshot,
    MemoryLoad,
    ProcessesSnapshot,
    ProcessInfo,
    Snapshot,
)


def run_demo_agent_loop(
    output_dir: Path, period: float, n_nodes: int, n_cpus: int, n_gpus: int
):
    """
    Simulate multiple nodes writing snapshots.
    """
    print(
        f"Starting Demo Agent: {n_nodes} nodes, {n_cpus} CPUs, {n_gpus} GPUs. Output: {output_dir}"
    )

    nodes = [f"node-{i:02d}" for i in range(n_nodes)]

    try:
        while True:
            timestamp = int(time.time())

            for hostname in nodes:
                # Generate CPU data
                cpus = []
                for i in range(n_cpus):
                    usage = random.uniform(0, 100)
                    cpus.append(CPUInfo(index=i, usage_percent=usage))

                # Generate Mem data (Total 256GB)
                total_mem = 256 * 1024**3
                used_mem = random.uniform(10, 200) * 1024**3
                memory = MemoryLoad(used_bytes=int(used_mem), total_bytes=total_mem)

                cpus_snap = CPUsSnapshot(cpus=cpus, memory=memory)

                # Generate GPU data
                gpus = []
                for i in range(n_gpus):
                    usage = random.uniform(0, 100)
                    total_vram = 32 * 1024**3  # 32GB
                    used_vram = random.uniform(0, 32) * 1024**3

                    gpus.append(
                        GPUInfo(
                            index=i,
                            name="Tesla V100-SXM2-32GB",
                            usage_percent=usage,
                            memory_load=MemoryLoad(
                                used_bytes=int(used_vram), total_bytes=total_vram
                            ),
                        )
                    )
                gpus_snap = GPUsSnapshot(gpus=gpus)

                # Generate Processes
                procs = []
                # Random number of processes 5-15
                for i in range(random.randint(5, 15)):
                    pid = random.randint(1000, 99999)
                    is_gpu = random.random() > 0.7

                    p_cpu_usage = random.uniform(0, 400)  # Multicore
                    p_mem = random.randint(100, 10000) * 1024**2

                    p_gpu_usage = 0.0
                    p_gpu_mem = 0
                    p_gpus_idx = []

                    if is_gpu and n_gpus > 0:
                        p_gpu_usage = random.uniform(10, 100)
                        p_gpu_mem = random.randint(1000, 10000) * 1024**2
                        g_idx = random.randint(0, n_gpus - 1)
                        p_gpus_idx = [g_idx]

                    procs.append(
                        ProcessInfo(
                            pid=pid,
                            name=f"python_proc_{i}",
                            cpu_usage_percent=p_cpu_usage,
                            cpu_memory_bytes=p_mem,
                            gpu_usage_percent=p_gpu_usage,
                            gpu_memory_bytes=p_gpu_mem,
                            cpus_indexes=[],  # Optional
                            gpus_indexes=p_gpus_idx,
                        )
                    )

                procs_snap = ProcessesSnapshot(processes=procs)

                snapshot = Snapshot(
                    timestamp=timestamp,
                    cpus_snapshot=cpus_snap,
                    gpus_snapshot=gpus_snap,
                    processes_snapshot=procs_snap,
                )

                file_path = output_dir / f"snapshot_{hostname}_{timestamp}.json"

                with open(file_path, "w") as f:
                    f.write(snapshot.json())

                # Cleanup old files for this node to prevent explosion
                # Simple cleanup: glob files for this node, keep latest 5
                existing = sorted(list(output_dir.glob(f"snapshot_{hostname}_*.json")))
                if len(existing) > 5:
                    for old_f in existing[:-5]:
                        try:
                            old_f.unlink()
                        except OSError:
                            pass

            time.sleep(period)

    except KeyboardInterrupt:
        print("Demo agent stopped.")


def run_demo_worker(
    output_dir: Path, period: float, n_nodes: int = 1, n_cpus: int = 4, n_gpus: int = 1
):
    p = Process(
        target=run_demo_agent_loop, args=(output_dir, period, n_nodes, n_cpus, n_gpus)
    )
    p.start()
    return p
