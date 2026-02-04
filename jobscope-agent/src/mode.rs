use clap::ValueEnum;

#[derive(Clone, Copy, Debug, ValueEnum)]
pub enum AgentMode {
    Local,
    Slurm,
}
