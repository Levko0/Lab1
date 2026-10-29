terraform {
  required_version = ">= 1.10"

   Uncomment and configure with your HCP Terraform organization and workspace:
   cloud {
     organization = "ooad-levko"
     workspaces {
       name = "successfulsuccess-dev"
     }
   }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      PROJECT_NAME = var.project_name
      ManagedBy    = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
