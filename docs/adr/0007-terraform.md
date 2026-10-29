# 7. Migrate Infrastructure from CloudFormation to Terraform

* Status: Accepted
* Deciders: Levko Zhuraiev
* Date: 2026-10-29

## Context and Problem Statement
In Labs 4, 5, and 6, our project's cloud infrastructure was deployed using individual AWS CloudFormation templates:
- `infra/auth.yml` (Cognito User Pool, Hosted UI Domain, Google Identity Provider, App Client)
- `infra/reports.yml` (Weekly reports architecture: S3 Bucket, SQS Queues, EventBridge Scheduler, VPC Endpoint, Report Builder & Mailer Lambdas)
- `infra/ai.yml` (Claude Haiku 4.5 Agenda Parser Lambda URL outside the VPC, Bedrock IAM permissions)

While CloudFormation functions effectively for monolithic single-account AWS workloads, it presents critical limitations as our system evolves:
1. **Cloud boundaries:** CloudFormation is strictly confined to AWS resources. It cannot manage or coordinate with external providers such as Google Cloud (OAuth 2.0 Client credentials), GitHub (CI/CD workflows and branch protection), or external DNS.
2. **Multi-environment and white-label scaling:** Supporting multiple environments (`dev`, `stage`, `prod`) or white-label deployments (e.g. `prod · rozetka`) in CloudFormation requires duplicating YAML templates or relying on cumbersome nested stacks.
3. **Circular dependencies:** Architectural dependencies, such as an S3 bucket requiring a Lambda permission while the Lambda requires bucket ARN references, forced brittle naming workarounds in CloudFormation.
4. **Drift and visibility:** CloudFormation drift detection must be manually requested, and change sets do not provide the unified, proactive plan-diffing workflow needed by a modern engineering team.

## Decision Drivers
* **Multi-provider and multi-cloud capability:** Single toolchain across AWS, Google Cloud, and GitHub.
* **Declarative state & plan-before-apply workflow:** Every change produces an explicit diff (`+`, `~`, `-`) before execution.
* **Separation of concerns:** Decoupling dependent resources (e.g., separating S3 bucket, Lambda permission, and bucket notification into distinct resources) to eliminate circular dependencies.
* **Centralized state locking & security:** Eliminating local state files and shared IAM long-term access keys via HCP Terraform and OIDC dynamic workload identity.

## Considered Options
1. **HashiCorp Terraform with HCP Terraform (Chosen)**
2. **AWS CloudFormation (Retain existing):** Native to AWS with managed state, but cannot manage non-AWS resources, suffers from slow rollback states, and lacks modular cross-cloud abstractions.
3. **AWS Cloud Development Kit (CDK):** Provides high-level imperative language constructs (TypeScript/Python), but compiles directly to CloudFormation stacks under the hood, inheriting all CloudFormation limitations and deployment bottlenecks.
4. **OpenTofu:** Excellent open-source fork with identical HCL syntax, but HCP Terraform provides managed remote runners, turnkey OIDC AWS federation, and native GitHub PR plan checks out of the box.

## Decision Outcome
We chose **Option 1: HashiCorp Terraform managed via HCP Terraform**.

The three CloudFormation templates are replaced with modular Terraform configuration files under `infra/`:
- `versions.tf`: Pins Terraform `>= 1.10`, required AWS and Archive providers, and configures the HCP Terraform `cloud` block.
- `variables.tf` & `terraform.tfvars`: Defines typed, validated inputs for all environments while strictly isolating secrets.
- `auth.tf`: Deploys Cognito User Pool, Domain prefix, Google IdP, App Client, and Managed Login Branding.
- `reports.tf`: Deploys S3 Bucket with lifecycle rules, SQS Queues with DLQ redrive, EventBridge Scheduler, S3 Gateway Endpoint, IAM roles, and Report Builder & Mailer functions.
- `ai.tf`: Deploys Claude Haiku Bedrock IAM role, Log Group, agenda parser Lambda, and public Function URL with CORS.
- `outputs.tf`: Exports all necessary endpoints, IDs, and URLs required by the application build and local development workflows.

### Specific Architectural Questions

1. **Why Terraform and not CloudFormation, CDK or OpenTofu, for this project?**
   Terraform enables unified orchestration across multiple providers (AWS for compute/storage/auth, Google Cloud for OAuth client credentials, and GitHub for repository governance) within a single execution plan. Unlike CDK, which still synthesizes CloudFormation templates and suffers from CloudFormation stack boundaries and rollback deadlocks, Terraform directly communicates with provider APIs and maintains an accurate state graph. HCP Terraform provides team collaboration, state locking, and OIDC runners without maintaining self-hosted CI infrastructure.

2. **Who can change the infrastructure now, and how?**
   Changes can only reach AWS through GitHub pull requests merged into `main`. 
   - A pull request automatically triggers an HCP Terraform speculative `plan` that is posted as a check for review.
   - Upon merge to `main`, HCP Terraform executes `apply` in Remote execution mode.
   - HCP Terraform assumes an AWS IAM role (`hcp-terraform-<org>`) via OIDC (`sts:AssumeRoleWithWebIdentity`), using short-lived tokens generated specifically for each run phase.
   - Developers no longer run `terraform apply` locally from their laptops; local access is strictly restricted to running `terraform plan` for validation.

3. **Where do the secrets end up, the state included?**
   - **Input secrets:** Sensitive variables (such as `google_client_secret` and `database_url`) are configured directly in HCP Terraform workspace variables marked as `sensitive = true` and `Environment / Terraform variables`. They are never committed to Git or `terraform.tfvars`.
   - **State file:** The state (`terraform.tfstate`) is stored exclusively in HCP Terraform, encrypted at rest using AES-256 with HashiCorp-managed keys and encrypted in transit via TLS 1.3. While sensitive values exist in plain JSON within the encrypted state file, access to the state is restricted via HCP Terraform RBAC permissions and audit logging.

4. **What happens if HCP Terraform is down?**
   - **Production runtime is unaffected:** Running AWS resources (Lambda, SQS, Cognito, Aurora, S3) are completely decoupled from Terraform and continue operating normally.
   - **Deployments pause:** New infrastructure changes cannot be applied until HCP Terraform recovers.
   - **Emergency break-glass procedure:** In the event of an extended outage during a critical incident, authorized engineers with emergency AWS IAM credentials can pull the latest state backup from version control / secure snapshot, reconfigure the backend locally or to an emergency S3/DynamoDB bucket, run `terraform plan`, and apply required emergency fixes.

## Consequences
* **Positive:**
  - Complete zero-downtime, non-destructive migration of existing resources via Terraform `import` blocks.
  - Eliminated CloudFormation S3 notification circular dependencies by cleanly separating `aws_s3_bucket`, `aws_lambda_permission`, and `aws_s3_bucket_notification`.
  - Zero permanent AWS IAM access keys stored on developer machines or GitHub repository secrets.
  - Standardized environment duplication via `.tfvars` files (`dev.tfvars`, `stage.tfvars`, `prod.tfvars`).
* **Negative:**
  - Terraform does not perform automatic rollbacks on partial apply failures; failures require fixing the code and reapplying.
  - Team members must understand HCL syntax and state management fundamentals.
