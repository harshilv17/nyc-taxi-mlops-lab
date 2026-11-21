# S0: security groups and rules. No SSH, no port 22: shell and UIs go through SSM.
#
# Ingress scope is a decision (decisions/): var.ingress_cidrs, set in terraform.tfvars.
# Host-to-host rules follow the ports in contracts/runtime.yaml.

resource "aws_security_group" "app" {
  name_prefix = "lab-app-"
  vpc_id      = data.aws_vpc.default.id
  description = "App host: Traefik on 80 from ingress_cidrs only"
}

resource "aws_security_group" "platform" {
  name_prefix = "lab-platform-"
  vpc_id      = data.aws_vpc.default.id
  description = "Platform host: MLflow from app; UIs via SSM port forwarding"
}

resource "aws_security_group" "llm" {
  name_prefix = "lab-llm-"
  vpc_id      = data.aws_vpc.default.id
  description = "LLM host: chat and embeddings from app and platform"
}

resource "aws_security_group" "rds" {
  name_prefix = "lab-rds-"
  vpc_id      = data.aws_vpc.default.id
  description = "RDS Postgres from app and platform"
}

# Hosts pull images and packages and there is no NAT: all egress open.
resource "aws_vpc_security_group_egress_rule" "all" {
  for_each = {
    app      = aws_security_group.app.id
    platform = aws_security_group.platform.id
    llm      = aws_security_group.llm.id
  }
  security_group_id = each.value
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# Outside world -> app, port 80 (Traefik).
resource "aws_vpc_security_group_ingress_rule" "app_http" {
  for_each          = toset(var.ingress_cidrs)
  security_group_id = aws_security_group.app.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = each.value
}

# app -> platform: MLflow.
resource "aws_vpc_security_group_ingress_rule" "platform_mlflow" {
  security_group_id            = aws_security_group.platform.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

# app, platform -> llm: chat (8080) and embeddings (8081).
resource "aws_vpc_security_group_ingress_rule" "llm" {
  for_each = {
    app_chat       = { src = aws_security_group.app.id, port = 8080 }
    app_embed      = { src = aws_security_group.app.id, port = 8081 }
    platform_chat  = { src = aws_security_group.platform.id, port = 8080 }
    platform_embed = { src = aws_security_group.platform.id, port = 8081 }
  }
  security_group_id            = aws_security_group.llm.id
  referenced_security_group_id = each.value.src
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

# app, platform -> rds: Postgres.
resource "aws_vpc_security_group_ingress_rule" "rds" {
  for_each = {
    app      = aws_security_group.app.id
    platform = aws_security_group.platform.id
  }
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
