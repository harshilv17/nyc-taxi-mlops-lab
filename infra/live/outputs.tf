# Names from contracts/runtime.yaml (terraform_outputs). scripts/ and the grader read them.

output "app_public_ip" {
  value = module.app.public_ip
}

output "app_instance_id" {
  value = module.app.instance_id
}

output "platform_instance_id" {
  value = module.platform.instance_id
}

output "llm_instance_id" {
  value = module.llm.instance_id
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "artifact_bucket" {
  value = module.artifacts.name
}

# Read later by scripts/catch-up.sh (S3, S6).
output "platform_private_ip" {
  value = module.platform.private_ip
}

output "llm_private_ip" {
  value = module.llm.private_ip
}
