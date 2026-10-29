variable "project_name" {
  type        = string
  description = "Prefix for the names of resources"
  default     = "successfulsuccess"
}

variable "region" {
  type        = string
  description = "AWS Region"
  default     = "us-east-1"
}

# --- Auth Variables (from auth.yml) ---

variable "callback_urls" {
  type        = list(string)
  description = "OIDC redirect_uri values: every URL the app serves from, with /auth/callback/ appended."
  default = [
    "http://localhost:3000/auth/callback/",
    "https://d27q0dddnqlp0w.cloudfront.net/auth/callback/"
  ]
}

variable "logout_urls" {
  type        = list(string)
  description = "Post-logout redirect URLs: where Cognito sends the user after sign-out."
  default = [
    "http://localhost:3000/auth/callback/",
    "https://d27q0dddnqlp0w.cloudfront.net/auth/callback/"
  ]
}

variable "google_client_id" {
  type        = string
  description = "OAuth client id of a Google Cloud Web application client. Empty leaves Google sign-in out."
  default     = "5113325550-1oc63tosfr03tv4qstgsrnmv86ripk0t.apps.googleusercontent.com"
}

variable "google_client_secret" {
  type        = string
  description = "That Google client's secret."
  sensitive   = true
  default     = ""
}

# --- Reports Variables (from reports.yml) ---

variable "vpc_id" {
  type        = string
  description = "VPC ID for S3 endpoint and report-builder Lambda"
  default     = "vpc-0f45811204f7241c8"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for report-builder Lambda"
  default = [
    "subnet-0daaf2be5dec61955",
    "subnet-03cf136be2c46758f",
    "subnet-00296dad4bb737a9c",
    "subnet-05736da0aa27f764c",
    "subnet-01152931280a3349b",
    "subnet-035085b24a26c10f6"
  ]
}

variable "route_table_ids" {
  type        = list(string)
  description = "Route table IDs for S3 VPC endpoint"
  default = [
    "rtb-09ea404613565894b"
  ]
}

variable "security_group_id" {
  type        = string
  description = "Security Group ID for report-builder Lambda"
  default     = "sg-090f7897ebf5a7592"
}

variable "image_uri" {
  type        = string
  description = "Docker image URI for backend Lambdas (builder, etc.)"
  default     = "219040782795.dkr.ecr.us-east-1.amazonaws.com/successfulsuccess-backend@sha256:93c890e952725e557da209780b9f8642236dfd2d34a8c404a86e9aef8e257b05"
}

variable "ai_image_uri" {
  type        = string
  description = "Docker image URI for AI agenda parser Lambda"
  default     = "219040782795.dkr.ecr.us-east-1.amazonaws.com/successfulsuccess-backend@sha256:aacf83767bd41115f978ce98affabf493a3aa095756af59e2e0de88dfc2f0940"
}

variable "architecture" {
  type        = string
  description = "Lambda architecture (arm64 or x86_64)"
  default     = "arm64"
}

variable "database_url" {
  type        = string
  description = "Async database connection string for report-builder"
  sensitive   = true
  default     = ""
}

variable "app_timezone" {
  type        = string
  description = "Application timezone"
  default     = "Europe/Kyiv"
}

variable "sender_email" {
  type        = string
  description = "SES sender email address"
  default     = "zhuraiev.pn@ucu.edu.ua"
}

variable "recipient_emails" {
  type        = string
  description = "SES recipient email addresses (comma separated)"
  default     = "zhuraiev.pn@ucu.edu.ua"
}

variable "schedule_expression" {
  type        = string
  description = "Schedule expression for weekly reports"
  default     = "cron(0 7 ? * MON *)"
}

# --- AI Variables (from ai.yml) ---

variable "allowed_origins" {
  type        = string
  description = "Allowed origins for CORS (comma separated)"
  default     = "https://d27q0dddnqlp0w.cloudfront.net"
}

variable "parser_model" {
  type        = string
  description = "Bedrock Claude model or inference profile ID"
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_region" {
  type        = string
  description = "AWS region for Bedrock calls"
  default     = "us-east-1"
}
