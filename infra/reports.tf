# S3 Gateway Endpoint
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.route_table_ids
}

# SQS Queues
resource "aws_sqs_queue" "report_dlq" {
  name = "report-requests-dlq"
}

resource "aws_sqs_queue" "report_queue" {
  name                       = "report-requests"
  visibility_timeout_seconds = 720

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.report_dlq.arn
    maxReceiveCount     = 3
  })
}

# EventBridge Scheduler Role & Schedule
resource "aws_iam_role" "scheduler" {
  name = "${var.project_name}-reports-SchedulerRole-gHlTVnISCxOi"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_send_message" {
  name = "SendReportMessageToQueue"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.report_queue.arn
    }]
  })
}

resource "aws_scheduler_schedule" "weekly_report" {
  name = "${var.project_name}-weekly-report"

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.app_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sqs_queue.report_queue.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      week   = null
      source = "schedule"
    })
  }
}

# Report Builder Lambda Role & Policies
resource "aws_iam_role" "report_builder" {
  name = "${var.project_name}-reports-ReportBuilderRole-9EvAto9ZMDEb"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "report_builder_vpc" {
  role       = aws_iam_role.report_builder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "report_builder_s3" {
  name = "S3PutReportPolicy"
  role = aws_iam_role.report_builder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "arn:aws:s3:::${var.project_name}-reports-${data.aws_caller_identity.current.account_id}/reports/*"
    }]
  })
}

resource "aws_iam_role_policy" "report_builder_sqs" {
  name = "SqsConsumeReportQueuePolicy"
  role = aws_iam_role.report_builder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ]
      Resource = aws_sqs_queue.report_queue.arn
    }]
  })
}

# Report Builder Function & Logs
resource "aws_cloudwatch_log_group" "report_builder" {
  name              = "/aws/lambda/${var.project_name}-report-builder"
  retention_in_days = 7
}

resource "aws_lambda_function" "report_builder" {
  function_name = "${var.project_name}-report-builder"
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.architecture]
  role          = aws_iam_role.report_builder.arn
  memory_size   = 512
  timeout       = 120

  image_config {
    command = ["app.reports.lambda_handler.handler"]
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      DATABASE_URL   = var.database_url
      APP_TIMEZONE   = var.app_timezone
      REPORTS_BUCKET = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.report_builder
  ]
}

# Event Source Mapping (SQS -> Report Builder)
resource "aws_lambda_event_source_mapping" "report_queue" {
  event_source_arn = aws_sqs_queue.report_queue.arn
  function_name    = aws_lambda_function.report_builder.arn
  batch_size       = 1
  enabled          = true
}

# Report Mailer Lambda Role & Policies
resource "aws_iam_role" "report_mailer" {
  name = "${var.project_name}-reports-ReportMailerRole-9ghFunlkUlot"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "report_mailer_basic" {
  role       = aws_iam_role.report_mailer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "report_mailer" {
  name = "MailerPermissions"
  role = aws_iam_role.report_mailer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.project_name}-reports-${data.aws_caller_identity.current.account_id}/reports/*"
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendRawEmail", "ses:SendEmail"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "report_mailer" {
  name              = "/aws/lambda/${var.project_name}-report-mailer"
  retention_in_days = 7
}

data "archive_file" "report_mailer" {
  type        = "zip"
  output_path = "${path.module}/report_mailer.zip"

  source {
    content  = <<-EOT
import json
import logging
import os
import urllib.parse
from email.message import EmailMessage
from pathlib import Path
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        raw_key = record["s3"]["object"]["key"]
        key = urllib.parse.unquote_plus(raw_key)

        logger.info("report-mailer triggered trigger=s3 key=%s", key)

        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key=key)
        csv_content = response["Body"].read()

        sender = os.environ["SENDER_EMAIL"]
        recipients = [r.strip() for r in os.environ["RECIPIENT_EMAILS"].split(",") if r.strip()]

        filename = Path(key).name
        msg = EmailMessage()
        msg["Subject"] = f"Weekly Meetings Report: {filename}"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(f"Attached is the weekly meetings report ({filename}).\n")
        msg.add_attachment(
            csv_content,
            maintype="text",
            subtype="csv",
            filename=filename,
        )

        ses = boto3.client("sesv2")
        ses.send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": recipients},
            Content={"Raw": {"Data": msg.as_bytes()}},
        )
    return {"status": "sent"}
EOT
    filename = "index.py"
  }
}

resource "aws_lambda_function" "report_mailer" {
  function_name    = "${var.project_name}-report-mailer"
  runtime          = "python3.12"
  handler          = "index.handler"
  role             = aws_iam_role.report_mailer.arn
  filename         = data.archive_file.report_mailer.output_path
  source_code_hash = data.archive_file.report_mailer.output_base64sha256
  memory_size      = 256
  timeout          = 60

  environment {
    variables = {
      SENDER_EMAIL     = var.sender_email
      RECIPIENT_EMAILS = var.recipient_emails
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.report_mailer
  ]
}

# Reports S3 Bucket, Lifecycle, and Notification
resource "aws_s3_bucket" "reports" {
  bucket = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket = aws_s3_bucket.reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "DeleteReportsAfter90Days"
    status = "Enabled"

    filter {
      prefix = "reports/"
    }

    expiration {
      days = 90
    }
  }
}

resource "aws_lambda_permission" "mailer_invoke" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.report_mailer.arn
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.reports.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "reports" {
  bucket = aws_s3_bucket.reports.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.report_mailer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.mailer_invoke]
}
