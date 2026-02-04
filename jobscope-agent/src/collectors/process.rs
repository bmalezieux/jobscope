use sysinfo::{System, Pid, ProcessRefreshKind, ProcessesToUpdate};
use nvml_wrapper::Nvml;
use nvml_wrapper::enums::device::UsedGpuMemory;
use std::collections::HashMap;
use std::fs;
use std::os::unix::fs::MetadataExt;
use crate::metrics::{ProcessesSnapshot, ProcessInfo, GPUIndex, CPUIndex};

pub fn refresh_user_processes(system: &mut System) {
    let my_uid = fs::metadata("/proc/self").map(|m| m.uid()).unwrap_or(0);
    let mut pids = Vec::new();

    if let Ok(entries) = fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() { continue; }
            
            if let Some(file_name) = path.file_name().and_then(|s| s.to_str()) {
                if let Ok(pid_val) = file_name.parse::<u32>() {
                    // Check owner
                    if let Ok(metadata) = fs::metadata(&path) {
                        if metadata.uid() == my_uid {
                            pids.push(Pid::from_u32(pid_val));
                        }
                    }
                }
            }
        }
    }
    
    // Also include existing PIDs to ensure they are checked (and removed if dead)
    for pid in system.processes().keys() {
        if !pids.contains(pid) {
            pids.push(*pid);
        }
    }
    
    system.refresh_processes_specifics(ProcessesToUpdate::Some(&pids), true, ProcessRefreshKind::everything());
}

/// Takes a snapshot of all running processes with their CPU and GPU usage
pub fn take_processes_snapshot(system: &System, nvml: Option<&Nvml>) -> ProcessesSnapshot {
    // First, collect GPU usage information indexed by PID
    let gpu_usage_map = if let Some(nvml) = nvml {
        _collect_gpu_usage(nvml)
    } else {
        HashMap::new()
    };
    
    // Get total CPU count to generate CPU indexes for active processes
    let cpu_count = system.cpus().len() as CPUIndex;
    
    // Then iterate through system processes and combine CPU + GPU data
    let processes: Vec<ProcessInfo> = system
        .processes()
        .iter()
        .map(|(pid, process)| {
            let pid_value = pid.as_u32() as crate::metrics::Pid;
            
            // Get GPU info for this process if it exists
            let (gpu_usage_percent, gpu_memory_bytes, gpus_indexes) = 
                gpu_usage_map.get(&(pid_value as u32))
                    .map(|gpu_info| (gpu_info.0, gpu_info.1, gpu_info.2.clone()))
                    .unwrap_or((0.0, 0, Vec::new()));
            
            // Generate CPU indexes based on CPU usage
            // If process is using CPU, assume it could run on any CPU
            let cpus_indexes = if process.cpu_usage() > 0.0 {
                (0..cpu_count).collect()
            } else {
                Vec::new()
            };
            
            ProcessInfo {
                pid: pid_value,
                name: process.name().to_str().map(|s| s.to_string()),
                cpu_usage_percent: process.cpu_usage(),
                cpu_memory_bytes: process.memory(),
                gpu_usage_percent,
                gpu_memory_bytes,
                cpus_indexes,
                gpus_indexes,
            }
        })
        .filter(|p| p.cpu_usage_percent > 0.0 || p.gpu_usage_percent > 0.0 || p.cpu_memory_bytes > 0)
        .collect();
    
    ProcessesSnapshot { processes }
}

/// Collects GPU usage information for all processes
/// Returns: HashMap<u32, (gpu_usage_percent, gpu_memory_bytes, Vec<GPUIndex>)>
fn _collect_gpu_usage(nvml: &Nvml) -> HashMap<u32, (f32, u64, Vec<GPUIndex>)> {
    let mut gpu_usage: HashMap<u32, (f32, u64, Vec<GPUIndex>)> = HashMap::new();
    let mut gpu_utilizations: HashMap<GPUIndex, f32> = HashMap::new();
    let mut gpu_total_memory: HashMap<GPUIndex, u64> = HashMap::new();
    
    let device_count = match nvml.device_count() {
        Ok(count) => count,
        Err(_) => return gpu_usage,
    };
    
    // First pass: collect GPU utilizations and total process memory per GPU
    for gpu_index in 0..device_count {
        let device = match nvml.device_by_index(gpu_index) {
            Ok(dev) => dev,
            Err(_) => continue,
        };
        
        // Get GPU utilization
        let gpu_util = match device.utilization_rates() {
            Ok(util) => util.gpu as f32,
            Err(_) => 0.0,
        };
        gpu_utilizations.insert(gpu_index, gpu_util);
        
        // Calculate total memory used by all processes on this GPU
        let mut total_proc_memory = 0u64;
        
        if let Ok(compute_procs) = device.running_compute_processes() {
            for proc_info in &compute_procs {
                if let UsedGpuMemory::Used(bytes) = proc_info.used_gpu_memory {
                    total_proc_memory += bytes;
                }
            }
        }
        
        if let Ok(graphics_procs) = device.running_graphics_processes() {
            for proc_info in &graphics_procs {
                if let UsedGpuMemory::Used(bytes) = proc_info.used_gpu_memory {
                    total_proc_memory += bytes;
                }
            }
        }
        
        gpu_total_memory.insert(gpu_index, total_proc_memory);
    }
    
    // Second pass: collect process information and calculate per-process GPU usage
    for gpu_index in 0..device_count {
        let device = match nvml.device_by_index(gpu_index) {
            Ok(dev) => dev,
            Err(_) => continue,
        };
        
        let gpu_util = gpu_utilizations.get(&gpu_index).copied().unwrap_or(0.0);
        let total_memory = gpu_total_memory.get(&gpu_index).copied().unwrap_or(1);
        
        // Get compute processes running on this GPU
        let compute_processes = match device.running_compute_processes() {
            Ok(procs) => procs,
            Err(_) => continue,
        };
        
        for proc_info in compute_processes {
            let pid = proc_info.pid;
            let memory = match proc_info.used_gpu_memory {
                UsedGpuMemory::Used(bytes) => bytes,
                UsedGpuMemory::Unavailable => 0,
            };
            
            // Estimate GPU usage based on memory proportion
            let usage_percent = if total_memory > 0 {
                (memory as f64 / total_memory as f64 * gpu_util as f64) as f32
            } else {
                0.0
            };
            
            gpu_usage.entry(pid)
                .and_modify(|(usage, mem, gpus)| {
                    *usage += usage_percent;
                    *mem += memory;
                    if !gpus.contains(&gpu_index) {
                        gpus.push(gpu_index);
                    }
                })
                .or_insert((usage_percent, memory, vec![gpu_index]));
        }
        
        // Also check graphics processes
        let graphics_processes = match device.running_graphics_processes() {
            Ok(procs) => procs,
            Err(_) => continue,
        };
        
        for proc_info in graphics_processes {
            let pid = proc_info.pid;
            let memory = match proc_info.used_gpu_memory {
                UsedGpuMemory::Used(bytes) => bytes,
                UsedGpuMemory::Unavailable => 0,
            };
            
            let usage_percent = if total_memory > 0 {
                (memory as f64 / total_memory as f64 * gpu_util as f64) as f32
            } else {
                0.0
            };
            
            gpu_usage.entry(pid)
                .and_modify(|(usage, mem, gpus)| {
                    *usage += usage_percent;
                    *mem += memory;
                    if !gpus.contains(&gpu_index) {
                        gpus.push(gpu_index);
                    }
                })
                .or_insert((usage_percent, memory, vec![gpu_index]));
        }
    }
    
    gpu_usage
}
