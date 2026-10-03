# Release images (018-app-cloud-deployment, FR-018, FR-032; research.md R5). In the base stack
# so they exist before the first push and survive every teardown.

locals {
  repositories = toset(["backend", "web"])
}

resource "aws_ecr_repository" "app" {
  for_each             = local.repositories
  name                 = "${local.prefix}-${each.key}-${local.env}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = local.repositories
  repository = aws_ecr_repository.app[each.key].name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the newest 5 release images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["v*"]
          countType      = "imageCountMoreThan"
          countNumber    = 5
        }
        action = { type = "expire" }
      },
    ]
  })
}
