# S0: root module wiring. Inputs in variables.tf, firewalls in security.tf, outputs in outputs.tf.

data "aws_vpc" "default" {
  default = true
}

# Hosts: one subnet, in var.availability_zone (us-east-1e lacks Graviton types).
data "aws_subnet" "hosts" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.availability_zone
  default_for_az    = true
}

# RDS wants subnets in at least two AZs. a/b/c only: 1e lacks some instance classes.
data "aws_subnets" "db" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "availability-zone"
    values = ["us-east-1a", "us-east-1b", "us-east-1c"]
  }
}

module "platform" {
  source             = "../modules/host"
  role               = "platform"
  instance_type      = var.platform_instance_type
  subnet_id          = data.aws_subnet.hosts.id
  security_group_ids = [aws_security_group.platform.id]
}

module "app" {
  source             = "../modules/host"
  role               = "app"
  instance_type      = var.app_instance_type
  subnet_id          = data.aws_subnet.hosts.id
  security_group_ids = [aws_security_group.app.id]
}

module "llm" {
  source             = "../modules/host"
  role               = "llm"
  instance_type      = var.llm_instance_type
  subnet_id          = data.aws_subnet.hosts.id
  security_group_ids = [aws_security_group.llm.id]
}

module "rds" {
  source             = "../modules/rds"
  instance_class     = var.rds_instance_class
  subnet_ids         = data.aws_subnets.db.ids
  security_group_ids = [aws_security_group.rds.id]
}

module "artifacts" {
  source = "../modules/bucket"
  name   = "lab-artifacts"
}

# Container only; the value is put out of band (see modules/secret).
module "wiki_secret" {
  source = "../modules/secret"
  name   = "lab/wiki"
}

# Grafana Cloud remote write for Alloy (S5): {"url", "user", "token"}. Container only; the value is put
# from the laptop with `aws secretsmanager put-secret-value`, so it never sits in state or GitHub.
module "grafana_secret" {
  source = "../modules/secret"
  name   = "lab/grafana"
}
