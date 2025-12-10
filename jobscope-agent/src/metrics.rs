use serde::Serialize;

pub type Pid = i32;
pub type CPUIndex = u32;
pub type GPUIndex = u32;


#[derive(Serialize)]
pub struct Snapshot {
    pub timestamp: i64,
    pub cpus_snapshot: CPUsSnapshot,
    pub gpus_snapshot: GPUsSnapshot,
    pub processes_snapshot: ProcessesSnapshot,
}

#[derive(Serialize)]
pub struct CPUsSnapshot {
    pub cpus: Vec<CPUInfo>,
    pub memory: MemoryLoad,
}

#[derive(Serialize)]
pub struct GPUsSnapshot {
    pub gpus: Vec<GPUInfo>,
}

#[derive(Serialize)]
pub struct ProcessesSnapshot {
    pub processes: Vec<ProcessInfo>,
}

#[derive(Serialize)]
pub struct MemoryLoad {
    pub used_bytes: u64,
    pub total_bytes: u64,
}

#[derive(Serialize)]
pub struct CPUInfo {
    pub index: CPUIndex,
    pub name: Option<String>,
    pub usage_percent: f32,
}

#[derive(Serialize)]
pub struct GPUInfo {
    pub index: GPUIndex,
    pub name: Option<String>,
    pub usage_percent: f32,
    pub memory_load: MemoryLoad,
}

#[derive(Serialize)]
pub struct ProcessInfo {
    pub pid: Pid,
    pub name: Option<String>,

    pub cpu_usage_percent: f32,
    pub cpu_memory_bytes: u64,

    pub gpu_usage_percent: f32,
    pub gpu_memory_bytes: u64,

    pub cpus_indexes: Vec<CPUIndex>,
    pub gpus_indexes: Vec<GPUIndex>,
}
    