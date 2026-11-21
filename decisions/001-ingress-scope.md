# 001: Ingress scope for the app host (port 80)

Stage: S0 · Date: 2026-11-21 · Author: harshilv17 · Drafted by agent: yes

## Choice

Port 80 on the app host accepts traffic from one address only: a single `/32`, the college network's public IP. The value is `ingress_cidrs` in `infra/live/terraform.tfvars`, which is gitignored, so the address isn't published in this public repo. The rule is applied in `infra/live/security.tf`.

## Rejected alternative

`0.0.0.0/0` (open to the internet). It would make the smoke test and demos easy from any network, and the grader could reach the app without waiting for its IP. I rejected it because the app has no authentication, so anyone could call `/predict`, and the repo is public, so the host's IP is easy to find.

Also considered and not picked: your IP plus the grader's IP (the grader's IP wasn't available), a wider college range such as a `/24` (more devices than needed), and no public port with SSM port forwarding only (conflicts with S0's public `curl` check).

## Why

- The college wifi reaches the internet through this one public IP, so a single `/32` already covers every device on it, including teammates.
- It is the smallest exposure that still meets the "done" check, `curl http://<app_public_ip>/version`, from the college network.
- A wider range adds reachable devices without adding anything I need. Opening to the world adds risk for convenience I don't need yet.
- Evidence at the time: `checkip.amazonaws.com` returned a single public IP on the college network.

## What would show this was wrong

- Port 80 stops answering from the college network. That means the college IP changed, so update `ingress_cidrs` and re-apply.
- The grader or a teammate off campus needs access. Then add their `/32` to the list.
- The college shows several outgoing IPs and the app is reachable only some of the time. Then a wider range is worth revisiting.
- Any sign of unwanted traffic to the app in the logs, even with this scope, would mean the app needs authentication rather than a firewall alone.
