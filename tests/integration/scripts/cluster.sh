#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
INTEGRATION_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
ROOT_DIR=$(cd "${INTEGRATION_DIR}/../.." && pwd)

COMPOSE_FILES=( -f "${INTEGRATION_DIR}/docker/docker-compose.yml" )
if [[ -n "${INTEGRATION_COMPOSE_OVERRIDE:-}" ]]; then
    COMPOSE_FILES+=( -f "${INTEGRATION_COMPOSE_OVERRIDE}" )
fi

PROJECT_NAME="${INTEGRATION_COMPOSE_PROJECT:-jobscope-integration}"
COMPOSE=( docker compose --project-name "${PROJECT_NAME}" --project-directory "${INTEGRATION_DIR}" "${COMPOSE_FILES[@]}" )
BASE_IMAGE="${SLURM_IMAGE_REPO:-ghcr.io/bmalezieux/slurm-docker-cluster}:${SLURM_VERSION:-25.05.3}"
SLURM_CTL_CONTAINER="slurm-docker-cluster-slurmctld"

usage() {
    cat <<'EOF'
Usage: tests/integration/scripts/cluster.sh <command> [options]

Commands:
  build           Pull the base Slurm image
  start           Build (default), start the cluster, and install jobscope
  install         Install jobscope inside slurmctld
  status          Show cluster status
  logs [service]  Tail logs (optionally for one service)
  stop            Stop the cluster
  down            Stop and remove volumes

Options (for start/build):
  --no-build      Skip image pull (start only)
  --no-install    Skip jobscope install
  --no-wait       Skip readiness wait
  --pull          Always pull base image before start
  --build-network Ignored (kept for backward compatibility)

Environment:
  SLURM_IMAGE_REPO, SLURM_VERSION  Override base image
  HTTP_PROXY, HTTPS_PROXY, NO_PROXY  Proxy settings (also passed into containers)
  INTEGRATION_COMPOSE_OVERRIDE      Additional compose file to include
  INTEGRATION_COMPOSE_PROJECT       Compose project name (default: jobscope-integration)
EOF
}

build_image() {
    local do_pull="${1:-0}"
    if [[ "${do_pull}" -eq 1 ]]; then
        echo "Pulling base image ${BASE_IMAGE}..."
        docker pull "${BASE_IMAGE}"
    fi
}

ensure_agent() {
    local agent="${ROOT_DIR}/jobscope-agent/target/release/jobscope-agent"
    if [[ ! -x "${agent}" ]]; then
        echo "Building jobscope-agent on host..."
        (cd "${ROOT_DIR}/jobscope-agent" && cargo build --release)
    fi
}

wait_for_cluster() {
    echo "Waiting for Slurm controller to be ready..."
    for _ in {1..30}; do
        if docker exec "${SLURM_CTL_CONTAINER}" scontrol ping &>/dev/null; then
            echo "Cluster is ready."
            return 0
        fi
        sleep 2
    done
    echo "Timed out waiting for Slurm cluster." >&2
    return 1
}

install_jobscope() {
    ensure_agent
    echo "Installing jobscope in slurmctld..."
    "${COMPOSE[@]}" exec -T slurmctld bash -lc '
        set -euo pipefail
        export PATH="/usr/local/bin:/root/.local/bin:${PATH}"

        if ! command -v curl >/dev/null; then
            if command -v apt-get >/dev/null; then
                apt-get update
                apt-get install -y --no-install-recommends curl ca-certificates
                rm -rf /var/lib/apt/lists/*
            elif command -v dnf >/dev/null; then
                dnf install -y --allowerasing curl ca-certificates
                dnf clean all
            elif command -v yum >/dev/null; then
                yum install -y curl ca-certificates
                yum clean all
            else
                echo "No supported package manager found to install curl/ca-certificates" >&2
                exit 1
            fi
        fi

        if ! command -v uv >/dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        fi

        if ! command -v cargo >/dev/null; then
            if command -v apt-get >/dev/null; then
                apt-get update
                apt-get install -y --no-install-recommends cargo rustc
                rm -rf /var/lib/apt/lists/*
            elif command -v dnf >/dev/null; then
                dnf install -y --allowerasing cargo rust
                dnf clean all
            elif command -v yum >/dev/null; then
                yum install -y cargo rust
                yum clean all
            else
                echo "No supported package manager found to install rust toolchain" >&2
                exit 1
            fi
        fi

        uv python install 3.12
        uv venv /root/jobscope-venv --python 3.12
        . /root/jobscope-venv/bin/activate
        uv pip install --no-cache-dir "maturin>=1.0,<2.0" puccinialin
        uv pip install -e /jobscope --no-build-isolation
    '
}

cmd="${1:-}"
shift || true

case "${cmd}" in
    build)
        build_network=""
        do_pull=0
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --pull) do_pull=1 ;;
                --build-network)
                    shift
                    build_network="${1:-}"
                    ;;
                *)
                    echo "Unknown option: $1" >&2
                    usage
                    exit 1
                    ;;
            esac
            shift
        done
        if [[ -n "${build_network}" ]]; then
            echo "Warning: --build-network is ignored (no image build step)." >&2
        fi
        build_image "${do_pull}"
        ;;
    start)
        do_build=1
        do_install=1
        do_wait=1
        build_network=""
        do_pull=0
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --no-build) do_build=0 ;;
                --no-install) do_install=0 ;;
                --no-wait) do_wait=0 ;;
                --pull) do_pull=1 ;;
                --build-network)
                    shift
                    build_network="${1:-}"
                    ;;
                *)
                    echo "Unknown option: $1" >&2
                    usage
                    exit 1
                    ;;
            esac
            shift
        done
        mkdir -p "${INTEGRATION_DIR}/.artifacts"
        if [[ "${do_build}" -eq 1 ]]; then
            if [[ -n "${build_network}" ]]; then
                echo "Warning: --build-network is ignored (no image build step)." >&2
            fi
            build_image "${do_pull}"
        fi
        "${COMPOSE[@]}" up -d --no-build
        if [[ "${do_wait}" -eq 1 ]]; then
            wait_for_cluster
        fi
        if [[ "${do_install}" -eq 1 ]]; then
            install_jobscope
        fi
        ;;
    install)
        install_jobscope
        ;;
    status)
        "${COMPOSE[@]}" ps
        ;;
    logs)
        if [[ $# -gt 0 ]]; then
            "${COMPOSE[@]}" logs -f "$1"
        else
            "${COMPOSE[@]}" logs -f
        fi
        ;;
    stop)
        "${COMPOSE[@]}" stop
        ;;
    down)
        "${COMPOSE[@]}" down -v
        ;;
    *)
        usage
        exit 1
        ;;
esac
