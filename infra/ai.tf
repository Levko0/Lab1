resource "aws_cloudwatch_log_group" "agenda_parser" {
  name              = "/aws/lambda/${var.project_name}-agenda-parser"
  retention_in_days = 7

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role" "agenda_parser" {
  name = "${var.project_name}-ai-FunctionRole-OH8BfxRKhs4z"

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

  tags = {
    PROJECT_NAME = var.project_name
  }
}

resource "aws_iam_role_policy_attachment" "agenda_parser_basic" {
  role       = aws_iam_role.agenda_parser.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "agenda_parser_bedrock" {
  name = "BedrockInvoke"
  role = aws_iam_role.agenda_parser.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ]
      Resource = [
        "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
        "arn:aws:bedrock:*::foundation-model/*"
      ]
    }]
  })
}

resource "aws_lambda_function" "agenda_parser" {
  function_name = "${var.project_name}-agenda-parser"
  description   = "Parses pasted meeting agendas with Claude Haiku 4.5"
  package_type  = "Image"
  image_uri     = var.ai_image_uri != "" ? var.ai_image_uri : var.image_uri
  architectures = [var.architecture]
  role          = aws_iam_role.agenda_parser.arn
  memory_size   = 512
  timeout       = 30

  image_config {
    command = ["app.ai.agenda_lambda.handler"]
  }

  environment {
    variables = {
      PARSER_MODEL         = var.parser_model
      BEDROCK_REGION       = var.bedrock_region
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.main.id
      COGNITO_REGION       = var.region
      APP_TIMEZONE         = var.app_timezone
    }
  }

  tags = {
    PROJECT_NAME = var.project_name
  }

  depends_on = [
    aws_cloudwatch_log_group.agenda_parser
  ]
}

resource "aws_lambda_function_url" "agenda_parser" {
  function_name      = aws_lambda_function.agenda_parser.function_name
  authorization_type = "NONE"
  invoke_mode        = "BUFFERED"

  cors {
    allow_methods = ["POST"]
    allow_headers = ["authorization", "content-type"]
    allow_origins = split(",", var.allowed_origins)
    max_age       = 86400
  }
}

resource "aws_lambda_permission" "agenda_parser_url" {
  statement_id           = "FunctionUrlAllowPublic"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.agenda_parser.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "agenda_parser_url_invoke" {
  statement_id             = "FunctionUrlAllowInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.agenda_parser.function_name
  principal                = "*"
  invoked_via_function_url = true
}
