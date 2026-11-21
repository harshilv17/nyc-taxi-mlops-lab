#!/usr/bin/env bash
# S0: register a lab host as a self-hosted GitHub Actions runner over SSM (no SSH).
#
#   scripts/register-runner.sh [app|platform|llm]     default: app
#
# The runner gets label lab-<role> (contracts/runtime.yaml). It runs as the `runner` user created by
# the host's first boot, as a systemd service, so it comes back by itself after a session restart.
# AWS access for jobs is the host's instance profile (decisions/002-runner-credentials.md): nothing
# from your session is copied to the host or to GitHub.
#
# Needs: AWS credentials in the environment, `gh` logged in, Terraform applied.
# The repo is public, so this refuses to run until fork-PR workflows need your approval.
set -euo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""

root="$(cd "$(dirname "$0")/.." && pwd)"
role=${1:-app}
case $role in app | platform | llm) ;; *) echo "usage: $0 [app|platform|llm]" >&2; exit 2 ;; esac
label=lab-$role

# Pinned (checksum from the release notes of actions/runner).
RUNNER_VERSION=2.338.2
RUNNER_SHA256=670adb2f268fe21dcbb58b3db0e0aa9d5b3bddfe2c651481336e561ff86de945

# `origin`, not gh's default: in a fork gh may resolve to the upstream template repo.
repo=$(git -C "$root" remote get-url origin | sed -E 's#.*github\.com[:/]##; s#\.git$##')

policy=$(gh api "repos/$repo/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy)
if [[ $policy != all_external_contributors ]]; then
  echo "refusing: fork-PR approval is '$policy'. Settings > Actions > General > 'Require approval for all external contributors', then re-run." >&2
  exit 1
fi

instance=$(terraform -chdir="$root/infra/live" output -raw "${role}_instance_id")
ping=$(aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$instance" \
  --query 'InstanceInformationList[0].PingStatus' --output text)
[[ $ping == Online ]] || { echo "$instance isn't reachable over SSM yet (status: $ping). First boot takes a few minutes: retry." >&2; exit 1; }

# Registration token: single use, expires in an hour. Never printed; it goes to the host in a 0600 temp
# file. ponytail: SSM keeps the command text in its history, so the token is readable there until it
# expires. Fine for a one-hour single-use token; if it ever matters, hand it over via Secrets Manager.
token=$(gh api -X POST "repos/$repo/actions/runners/registration-token" --jq .token)
params=$(mktemp)
trap 'rm -f "$params"' EXIT
chmod 600 "$params"

read -r -d '' remote <<EOF || true
set -euo pipefail
for _ in \$(seq 1 120); do [ -f /var/lib/lab-setup-done ] && break; sleep 5; done
[ -f /var/lib/lab-setup-done ] || { echo "first boot hasn't finished" >&2; exit 1; }
cd /opt/actions-runner
if [ ! -f .runner ]; then
  curl -fsSL -o runner.tgz "https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/actions-runner-linux-arm64-$RUNNER_VERSION.tar.gz"
  echo "$RUNNER_SHA256  runner.tgz" | sha256sum -c -
  sudo -H -u runner tar xzf runner.tgz
  rm runner.tgz
  sudo -H -u runner ./config.sh --unattended --replace --url "https://github.com/$repo" \
    --token "$token" --name "$label" --labels "$label"
fi
ls /etc/systemd/system/actions.runner.*.service >/dev/null 2>&1 || ./svc.sh install runner
./svc.sh start
./svc.sh status | head -5
EOF
jq -n --arg c "$remote" '{commands: [$c]}' >"$params"

cmd=$(aws ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
  --parameters "file://$params" --timeout-seconds 900 --query Command.CommandId --output text)
echo "SSM command $cmd sent to $instance ($label)"
aws ssm wait command-executed --command-id "$cmd" --instance-id "$instance" || true
aws ssm get-command-invocation --command-id "$cmd" --instance-id "$instance" \
  --query '{status: Status, out: StandardOutputContent, err: StandardErrorContent}' --output json |
  jq -r '"status: \(.status)\n\(.out)\n\(.err)"' | sed "s/$token/<token>/g"

# The runner shows up in GitHub once it has connected.
for _ in $(seq 1 12); do
  state=$(gh api "repos/$repo/actions/runners" --jq ".runners[] | select(.name == \"$label\") | .status") || state=
  [[ $state == online ]] && { echo "runner $label is online"; exit 0; }
  sleep 5
done
echo "runner $label isn't online in GitHub yet: check the output above" >&2
exit 1
