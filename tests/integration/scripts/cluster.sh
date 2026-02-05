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
IMAGE_TAG="jobscope/slurm-test:${SLURM_VERSION:-25.05.3}"
BASE_IMAGE="${SLURM_IMAGE_REPO:-ghcr.io/bmalezieux/slurm-docker-cluster}:${SLURM_VERSION:-25.05.3}"
SLURM_CTL_CONTAINER="slurm-docker-cluster-slurmctld"

usage() {
    cat <<'EOF'
Usage: tests/integration/scripts/cluster.sh <command> [options]

Commands:
  build           Build the Slurm test image
  start           Build (default), start the cluster, and install jobscope
  install         Install jobscope inside slurmctld
  status          Show cluster status
  logs [service]  Tail logs (optionally for one service)
  stop            Stop the cluster
  down            Stop and remove volumes

Options (for start/build):
  --no-build      Skip image build (start only)
  --no-install    Skip jobscope install
  --no-wait       Skip readiness wait
  --pull          Always pull base image during build
  --no-cache      Disable build cache
  --build-network Set docker build network (e.g. host)

Environment:
  SLURM_IMAGE_REPO, SLURM_VERSION  Override base image
  HTTP_PROXY, HTTPS_PROXY, NO_PROXY  Proxy settings (also passed into containers)
  INTEGRATION_COMPOSE_OVERRIDE      Additional compose file to include
  INTEGRATION_COMPOSE_PROJECT       Compose project name (default: jobscope-integration)
EOF
}

build_image() {
    local build_network="${1:-}"
    shift || true
    local extra_args=()

    for arg in "$@"; do
        case "${arg}" in
            --pull) extra_args+=(--pull) ;;
            --no-cache) extra_args+=(--no-cache) ;;
        esac
    done

    if [[ -n "${build_network}" ]]; then
        extra_args+=(--network "${build_network}")
    fi

    docker build \
        -f "${INTEGRATION_DIR}/docker/Dockerfile.slurm-test" \
        -t "${IMAGE_TAG}" \
        --build-arg "SLURM_BASE_IMAGE=${BASE_IMAGE}" \
        --build-arg "HTTP_PROXY=${HTTP_PROXY-}" \
        --build-arg "HTTPS_PROXY=${HTTPS_PROXY-}" \
        --build-arg "NO_PROXY=${NO_PROXY-}" \
        "${extra_args[@]}" \
        "${ROOT_DIR}"
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
        if [ ! -x /root/jobscope-venv/bin/python ]; then
            uv venv /root/jobscope-venv --python 3.12
        fi
        . /root/jobscope-venv/bin/activate
        if [ -f /root/jobscope-venv/.jobscope_deps_installed ]; then
            uv pip install -e /jobscope --no-deps
        else
            uv pip install -e /jobscope
        fi
    '
}

cmd="${1:-}"
shift || true

case "${cmd}" in
    build)
        build_args=()
        build_network=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --pull) build_args+=(--pull) ;;
                --no-cache) build_args+=(--no-cache) ;;
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
        build_image "${build_network}" "${build_args[@]}"
        ;;
    start)
        do_build=1
        do_install=1
        do_wait=1
        build_args=()
        build_network=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --no-build) do_build=0 ;;
                --no-install) do_install=0 ;;
                --no-wait) do_wait=0 ;;
                --pull) build_args+=(--pull) ;;
                --no-cache) build_args+=(--no-cache) ;;
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
            build_image "${build_network}" "${build_args[@]}"
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
