# Read by deploy/app. The inputs that shape user-data are echoed so that `allow` can re-apply
# with the running instance's own values and never replace it by accident (FR-029).

output "instance_id" {
  value = aws_instance.app.id
}

output "public_ip" {
  value     = aws_instance.app.public_ip
  sensitive = true
}

output "release" {
  value = var.release
}

output "ami_id" {
  value = var.ami_id
}

output "backend_digest" {
  value = var.backend_digest
}

output "web_digest" {
  value = var.web_digest
}

output "db_init_args" {
  value = var.db_init_args
}
