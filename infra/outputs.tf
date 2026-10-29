output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = aws_cognito_user_pool_client.main.id
}

output "issuer" {
  description = "The iss of every token; its signing keys are at <Issuer>/.well-known/jwks.json"
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}

output "hosted_domain" {
  description = "Cognito OAuth hosted domain"
  value       = "${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "google_redirect_uri" {
  description = "Add this to the Google client Authorized redirect URIs"
  value       = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com/oauth2/idpresponse"
}

output "google_enabled" {
  description = "Whether Google sign-in is enabled"
  value       = var.google_client_id != ""
}

output "reports_bucket_name" {
  description = "S3 bucket name for weekly reports"
  value       = aws_s3_bucket.reports.bucket
}

output "queue_url" {
  description = "SQS queue URL for report requests"
  value       = aws_sqs_queue.report_queue.url
}

output "builder_function_name" {
  description = "Lambda function name for report builder"
  value       = aws_lambda_function.report_builder.function_name
}

output "mailer_function_name" {
  description = "Lambda function name for report mailer"
  value       = aws_lambda_function.report_mailer.function_name
}

output "parser_url" {
  description = "Agenda parser function URL (without trailing slash)"
  value       = trimsuffix(aws_lambda_function_url.agenda_parser.function_url, "/")
}

output "parser_function_name" {
  description = "Agenda parser Lambda function name"
  value       = aws_lambda_function.agenda_parser.function_name
}
