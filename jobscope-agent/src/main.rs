mod collectors;
mod metrics;
mod mode;

use sysinfo::System;
use nvml_wrapper::Nvml;
use clap::Parser;
use crate::mode::AgentMode;


fn main() {

    let cli = Cli::parse();
    let output_folder = &cli.output;
    let period = cli.period;
    let mode = cli.mode;

    // Initialize sysinfo System
    let mut system = System::new();
    
    // Initialize NVML for GPU monitoring
    let nvml = match Nvml::init() {
        Ok(nvml) => Some(nvml),
        Err(e) => {
            eprintln!("Failed to initialize NVML: {}", e);
            eprintln!("GPU monitoring will not be available");
            None
        }
    };

    // First refresh to initialize counters
    system.refresh_memory();
    system.refresh_cpu_usage();
    collectors::process::refresh_user_processes(&mut system);

    // If not continuous, we need a small delay to get CPU usage
    if !cli.continuous {
        std::thread::sleep(std::time::Duration::from_millis(200));
        system.refresh_memory();
        system.refresh_cpu_usage();
        collectors::process::refresh_user_processes(&mut system);
        if let Err(e) = take_and_save_snapshot(&system, nvml.as_ref(), output_folder, mode) {
            eprintln!("Error taking snapshot: {}", e);
        }
        return;
    }

    println!("Starting continuous monitoring with period {}s", period);
    
    loop {
        // Wait for the period
        std::thread::sleep(std::time::Duration::from_secs_f64(period));
        
        // Refresh and take snapshot
        system.refresh_memory();
        system.refresh_cpu_usage();
        collectors::process::refresh_user_processes(&mut system);

        if let Err(e) = take_and_save_snapshot(&system, nvml.as_ref(), output_folder, mode) {
            eprintln!("Error taking snapshot: {}", e);
        }
    }
}

fn take_and_save_snapshot(
    system: &System,
    nvml: Option<&Nvml>,
    output_folder: &str,
    mode: AgentMode,
) -> Result<(), Box<dyn std::error::Error>> {
    match collectors::take_global_snapshot(system, nvml, output_folder, mode) {
        Ok(filepath) => {
            println!("Snapshot saved to: {}", filepath);
            Ok(())
        },
        Err(e) => Err(e),
    }
}

#[derive(Parser)]
#[command(name = "JobScope Agent")]
#[command(about = "Agent for monitoring job resource usage", long_about = None)]
struct Cli {
    /// Output folder for snapshots
    #[arg(short, long, default_value = "./snapshots")]
    output: String,

    /// Run continuously
    #[arg(long, default_value_t = false)]
    continuous: bool,

    /// Sampling period in seconds
    #[arg(short, long, default_value_t = 2.0)]
    period: f64,

    /// Resource accounting mode
    #[arg(long, value_enum, default_value_t = AgentMode::Local)]
    mode: AgentMode,
}
