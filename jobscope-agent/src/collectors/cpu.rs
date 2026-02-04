use crate::metrics::{CPUIndex, CPUInfo, CPUsSnapshot, MemoryLoad};
use crate::mode::AgentMode;
use std::fs;
use sysinfo::System;

fn read_allowed_cpus_from_status() -> Option<Vec<usize>> {
    let status = fs::read_to_string("/proc/self/status").ok()?;
    for line in status.lines() {
        if let Some(rest) = line.strip_prefix("Cpus_allowed_list:") {
            return Some(parse_cpu_list(rest.trim()));
        }
    }
    None
}

fn parse_cpu_list(list_str: &str) -> Vec<usize> {
    let mut cpus = Vec::new();
    for part in list_str.split(',').map(str::trim).filter(|s| !s.is_empty()) {
        if let Some((start, end)) = part.split_once('-') {
            if let (Ok(s), Ok(e)) = (start.parse::<usize>(), end.parse::<usize>()) {
                for i in s..=e {
                    cpus.push(i);
                }
            }
        } else if let Ok(i) = part.parse::<usize>() {
            cpus.push(i);
        }
    }
    cpus
}

// Returns (path, is_v2)
fn get_cgroup_memory_path() -> Option<(String, bool)> {
    // v2 is typically "0::/some/path".
    // v1 has controllers like "5:memory:/some/path".
    let cgroup = fs::read_to_string("/proc/self/cgroup").ok()?;

    for line in cgroup.lines() {
        let mut parts = line.split(':');
        let _hier = parts.next()?;
        let controllers = parts.next()?;
        let path = parts.next()?;

        let is_unified_v2 = controllers.is_empty();
        let has_memory_v1 = controllers.split(',').any(|c| c == "memory");

        if is_unified_v2 {
            return Some((format!("/sys/fs/cgroup{}", path), true));
        }
        if has_memory_v1 {
            return Some((format!("/sys/fs/cgroup/memory{}", path), false));
        }
    }

    None
}

fn read_u64(path: &str) -> Option<u64> {
    fs::read_to_string(path).ok()?.trim().parse::<u64>().ok()
}

fn read_cgroup_memory_limit_bytes() -> Option<u64> {
    let (path, is_v2) = get_cgroup_memory_path()?;

    if is_v2 {
        let s = fs::read_to_string(format!("{}/memory.max", path)).ok()?;
        let s = s.trim();
        if s == "max" {
            return None;
        }
        return s.parse::<u64>().ok();
    }

    // v1
    let limit = read_u64(&format!("{}/memory.limit_in_bytes", path))?;
    // Some setups report an effectively-unlimited value; ignore obvious bogus huge numbers.
    if limit >= (1u64 << 60) {
        return None;
    }
    Some(limit)
}

fn read_cgroup_memory_usage_bytes() -> Option<(u64, Option<u64>)> {
    let (path, is_v2) = get_cgroup_memory_path()?;
    if is_v2 {
        let current = read_u64(&format!("{}/memory.current", path))?;
        let peak = read_u64(&format!("{}/memory.peak", path));
        return Some((current, peak));
    }

    let current = read_u64(&format!("{}/memory.usage_in_bytes", path))?;
    let peak = read_u64(&format!("{}/memory.max_usage_in_bytes", path));
    Some((current, peak))
}

pub fn take_cpus_snapshot(system: &System, mode: AgentMode) -> CPUsSnapshot {
    let (cpu_indices, fallback_cpu_count) = match mode {
        AgentMode::Local => (None, None),
        AgentMode::Slurm => {
            let cpuset = read_allowed_cpus_from_status();
            let env_count = std::env::var("SLURM_CPUS_ON_NODE").ok().and_then(|v| v.parse::<usize>().ok());
            (cpuset, env_count)
        }
    };

    let mut cpus_info: Vec<CPUInfo> = Vec::new();
    for (index, cpu) in system.cpus().iter().enumerate() {
        let include = if let Some(ref allowed) = cpu_indices {
            allowed.contains(&index)
        } else if let Some(n) = fallback_cpu_count {
            index < n
        } else {
            true
        };

        if include {
            cpus_info.push(CPUInfo {
                index: index as CPUIndex,
                name: Some(cpu.name().to_string()),
                usage_percent: cpu.cpu_usage(),
            });
        }
    }

    let memory = match mode {
        AgentMode::Local => MemoryLoad {
            used_bytes: system.used_memory(),
            total_bytes: system.total_memory(),
            max_used_bytes: None,
        },
        AgentMode::Slurm => {
            let total = read_cgroup_memory_limit_bytes().unwrap_or_else(|| system.total_memory());
            let (used, peak) = read_cgroup_memory_usage_bytes().unwrap_or_else(|| (system.used_memory(), None));
            MemoryLoad {
                used_bytes: used,
                total_bytes: total,
                max_used_bytes: peak,
            }
        }
    };

    CPUsSnapshot {
        cpus: cpus_info,
        memory,
    }
}