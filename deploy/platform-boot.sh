#!/usr/bin/env bash
# Platform host, at every boot (S4, decisions/012): bring Dagster back once RDS accepts connections.
#
# Why: after a host start, Dagster's code server imports labpipes.definitions, which needs RDS. If RDS
# isn't up yet the import gives up after a few minutes ("too many retries for DB connection"), the
# container stays "healthy" holding that error, and the webserver and daemon keep "Error loading
# repository location labpipes" until someone restarts them (runbooks/restore.md, row 4). MLflow and
# serving retry on their own; Dagster doesn't.
#
#   deploy/platform-boot.sh            on the host (the systemd unit runs this)
#   deploy/platform-boot.sh install    from your laptop: installs and enables the unit over SSM
#
# What it does: every 30 s, if Dagster answers with a loaded code location, stop (done). Otherwise, once
# RDS accepts a TCP connection, restart the code server, then the webserver and daemon. At most 3 restarts.
# What it never does: start, stop or change any AWS resource (RDS stays the person's to start), touch
# MLflow or serving, or loop restarting containers forever.
set -euo pipefail

if [[ ${1:-} == install ]]; then
  export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
  root="$(cd "$(dirname "$0")/.." && pwd)"
  instance=$(terraform -chdir="$root/infra/live" output -raw platform_instance_id)
  script=$(base64 <"$0" | tr -d '\n')
  read -r -d '' remote <<EOF || true
set -euo pipefail
echo $script | base64 -d > /usr/local/bin/lab-platform-boot
chmod 755 /usr/local/bin/lab-platform-boot
cat > /etc/systemd/system/lab-platform-boot.service <<'UNIT'
[Unit]
Description=Bring Dagster back once RDS accepts connections (nyc-taxi-mlops-lab S4)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lab-platform-boot
TimeoutStartSec=infinity

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable lab-platform-boot.service
systemctl is-enabled lab-platform-boot.service
EOF
  params=$(mktemp)
  trap 'rm -f "$params"' EXIT
  jq -n --arg c "$remote" '{commands: [$c]}' >"$params"
  cmd=$(aws ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
    --parameters "file://$params" --query Command.CommandId --output text)
  aws ssm wait command-executed --command-id "$cmd" --instance-id "$instance" || true
  aws ssm get-command-invocation --command-id "$cmd" --instance-id "$instance" \
    --query '[Status, StandardOutputContent, StandardErrorContent]' --output text
  exit 0
fi

log() { echo "lab-platform-boot: $*"; }
loaded() { docker exec platform-webserver-1 python -m labpipes.status >/dev/null 2>&1; }
rds_up() { # a TCP connection to the RDS endpoint (from the lab/rds secret), from inside the stack
  docker exec platform-webserver-1 python -c '
import socket
from labpipes.runtime import storage_env
e = storage_env()
socket.create_connection((e["DAGSTER_PG_HOST"], int(e.get("DAGSTER_PG_PORT", 5432))), 5).close()' >/dev/null 2>&1
}

restarts=0
while true; do
  if loaded; then log "Dagster code location loaded"; exit 0; fi
  if rds_up; then
    if ((restarts == 3)); then log "still not loaded after 3 restarts: see runbooks/restore.md"; exit 1; fi
    restarts=$((restarts + 1))
    log "RDS accepts connections, code location not loaded: restarting Dagster ($restarts/3)"
    docker restart platform-code-1 >/dev/null
    for _ in $(seq 1 30); do
      [[ $(docker inspect -f '{{.State.Health.Status}}' platform-code-1) == healthy ]] && break
      sleep 5
    done
    docker restart platform-webserver-1 platform-daemon-1 >/dev/null
    sleep 30  # the webserver loads the workspace before `loaded` can answer
  else
    sleep 30  # RDS is stopped or still starting: starting it is the person's job (scripts/restore.sh)
  fi
done
