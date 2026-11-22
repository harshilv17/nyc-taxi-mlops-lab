#!/usr/bin/env bash
# Bring the lab back after a session end (S4, decisions/012; runbooks/restore.md is the manual version).
# Run it yourself after Start Lab and pasting the new credentials into ~/.aws/credentials:
#
#   scripts/restore.sh
#
# What it does: start RDS if it's stopped and resume Redshift if it's paused (in parallel), wait until
# both are available, then run the status workflow and scripts/health.sh. Dagster's restart after RDS is
# the platform host's boot unit (deploy/platform-boot.sh); MLflow and serving come back on their own.
# What it never does: stop, pause or delete anything, start the notebook (nothing but exploration
# needs it), run terraform, or move a model alias. Exit status is health.sh's.
set -euo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
root="$(cd "$(dirname "$0")/.." && pwd)"
repo=$(git -C "$root" remote get-url origin | sed -E 's#.*github\.com[:/]##; s#\.git$##')
t0=$SECONDS
took() { echo "$(( (SECONDS - t0) / 60 ))m$(( (SECONDS - t0) % 60 ))s"; }

# A cancelled session's keys still pass sts get-caller-identity; everything else is denied.
aws rds describe-db-instances --db-instance-identifier lab --query 'DBInstances[0].DBInstanceStatus' --output text >/dev/null ||
  { echo "AWS calls are denied: Start Lab and paste this session's credentials into ~/.aws/credentials" >&2; exit 1; }

rds=$(aws rds describe-db-instances --db-instance-identifier lab --query 'DBInstances[0].DBInstanceStatus' --output text)
rs=$(aws redshift describe-clusters --cluster-identifier lab --query 'Clusters[0].ClusterStatus' --output text)
echo "rds: $rds, redshift: $rs"
[[ $rds == stopped ]] && aws rds start-db-instance --db-instance-identifier lab --query DBInstance.DBInstanceStatus --output text
[[ $rs == paused ]] && aws redshift resume-cluster --cluster-identifier lab --query Cluster.ClusterStatus --output text

aws rds wait db-instance-available --db-instance-identifier lab && echo "rds available after $(took)"
aws redshift wait cluster-available --cluster-identifier lab && echo "redshift available after $(took)"

# Riders: serving reloads @champion within ~30 s of MLflow being back; Dagster within a few minutes (boot unit).
gh workflow run status.yaml -R "$repo"
sleep 10
run=$(gh run list -R "$repo" -w status -L1 --json databaseId -q '.[0].databaseId')
if gh run watch "$run" -R "$repo" --exit-status >/dev/null 2>&1; then
  echo "status run $run green after $(took)"
else
  echo "status run $run failed: if it says 'code location not loaded yet', see runbooks/restore.md row 4" >&2
fi
"$root/scripts/health.sh"
