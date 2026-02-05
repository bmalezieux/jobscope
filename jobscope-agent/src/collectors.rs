pub mod cpu;
pub mod gpu;
pub mod process;

use sysinfo::System;
use nvml_wrapper::Nvml;
use std::fs;
use std::io::Write;
use std::path::Path;
use crate::metrics::Snapshot;
use crate::mode::AgentMode;


pub fn take_global_snapshot(
    system: &System,
    nvml: Option<&Nvml>,
    output_folder: &str,
    mode: AgentMode,
) -> Result<String, Box<dyn std::error::Error>> {
    // Create output folder if it doesn't exist
    fs::create_dir_all(output_folder)?;

    // Get current timestamp (seconds since epoch)
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_secs() as i64;

    // Collect snapshots from all subsystems
    let cpus_snapshot = cpu::take_cpus_snapshot(system, mode);
    let gpus_snapshot = gpu::take_gpus_snapshot(nvml);
    let processes_snapshot = process::take_processes_snapshot(system, nvml);

    // Build the complete snapshot
    let snapshot = Snapshot {
        timestamp,
        cpus_snapshot,
        gpus_snapshot,
        processes_snapshot,
    };

    // Serialize to JSON
    let json_data = serde_json::to_string_pretty(&snapshot)?;

    // Create filename with timestamp and hostname
    let hostname = System::host_name().unwrap_or_else(|| "unknown".to_string());
    let filename = format!("snapshot_{}_{}.json", hostname, timestamp);
    let filepath = Path::new(output_folder).join(&filename);

    // Write to file
    let mut file = fs::File::create(&filepath)?;
    file.write_all(json_data.as_bytes())?;

    Ok(filepath.to_string_lossy().to_string())
}