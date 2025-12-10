use std::process::{Command, exit};
use std::env;

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    
    let status = Command::new("python")
        .arg("-m")
        .arg("jobscope")
        .args(&args)
        .status()
        .expect("Failed to execute python");

    if let Some(code) = status.code() {
        exit(code);
    } else {
        exit(1);
    }
}
