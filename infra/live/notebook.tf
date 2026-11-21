# S2: the SageMaker notebook (infra/modules/notebook) for exploration. It clones your public repo
# (var.github_repo, set in terraform.tfvars) and reads its settings from ~/SageMaker/.lab.env.

module "notebook" {
  source    = "../modules/notebook"
  subnet_id = data.aws_subnet.hosts.id
  repo_url  = "https://github.com/${var.github_repo}"
  env = {
    MLFLOW_TRACKING_URI = "http://${module.platform.private_ip}:5000"
    REDSHIFT_CLUSTER_ID = module.warehouse.cluster_id
    REDSHIFT_DATABASE   = module.warehouse.database
    REDSHIFT_DB_USER    = module.warehouse.admin_user
  }
}

# notebook -> platform: MLflow (runtime.yaml: port 5000). Nothing else on the platform host is opened to it.
resource "aws_vpc_security_group_ingress_rule" "platform_mlflow_notebook" {
  security_group_id            = aws_security_group.platform.id
  referenced_security_group_id = module.notebook.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

output "notebook_name" {
  value = module.notebook.name
}
