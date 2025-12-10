use sysinfo::System;
use crate::metrics::{CPUsSnapshot, CPUInfo, MemoryLoad, CPUIndex};

pub fn take_cpus_snapshot(system: &System) -> CPUsSnapshot {
    let cpus_info = system
        .cpus()
        .iter()
        .enumerate()
        .map(|(index, cpu)| _collect_cpu_info(index as CPUIndex, cpu))
        .collect();

    CPUsSnapshot {
        cpus: cpus_info,
        memory: MemoryLoad {
            used_bytes: system.used_memory(),
            total_bytes: system.total_memory(),
        },
    }
}

fn _collect_cpu_info(index: u32, cpu: &sysinfo::Cpu) -> CPUInfo {
    CPUInfo {
        index: index as CPUIndex,
        name: Some(cpu.name().to_string()),
        usage_percent: cpu.cpu_usage(),
    }
}