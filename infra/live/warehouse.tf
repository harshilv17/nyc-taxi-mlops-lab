# S1: the Redshift warehouse (infra/modules/redshift), one ra3.large node.
# Clients use the Data API, so the module opens no ingress. Same subnets as RDS (a/b/c).

module "warehouse" {
  source            = "../modules/redshift"
  subnet_ids        = data.aws_subnets.db.ids
  availability_zone = var.availability_zone
}

# Names from contracts/platform.yaml (terraform_outputs).
output "redshift_cluster_id" {
  value = module.warehouse.cluster_id
}

output "redshift_database" {
  value = module.warehouse.database
}
