use nvml_wrapper::Nvml;
use crate::metrics::{GPUsSnapshot, GPUInfo, GPUIndex, MemoryLoad};


pub fn take_gpus_snapshot(nvml: Option<&Nvml>) -> GPUsSnapshot {
    let nvml = match nvml {
        Some(n) => n,
        None => return GPUsSnapshot { gpus: Vec::new() },
    };

    let device_count = match nvml.device_count() {
        Ok(count) => count,
        Err(_) => 0,
    };

    let gpus_info = (0..device_count)
        .filter_map(|index| _collect_gpu_info(nvml, index as GPUIndex))
        .collect();

    GPUsSnapshot { gpus: gpus_info }
}

fn _collect_gpu_info(nvml: &Nvml, index: GPUIndex) -> Option<GPUInfo> {
    let device = match nvml.device_by_index(index as u32) {
        Ok(dev) => dev,
        Err(_) => return None,
    };

    let name = match device.name() {
        Ok(n) => Some(n),
        Err(_) => None,
    };

    let utilization = match device.utilization_rates() {
        Ok(util) => util,
        Err(_) => return None,
    };

    let memory_info = match device.memory_info() {
        Ok(mem) => mem,
        Err(_) => return None,
    };

    Some(GPUInfo {
        index,
        name,
        usage_percent: utilization.gpu as f32,
        memory_load: MemoryLoad {
            used_bytes: memory_info.used,
            total_bytes: memory_info.total,
        },
    })
}