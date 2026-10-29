project_name     = "successfulsuccess"
region           = "us-east-1"
google_client_id = "5113325550-1oc63tosfr03tv4qstgsrnmv86ripk0t.apps.googleusercontent.com"
vpc_id           = "vpc-0f45811204f7241c8"
subnet_ids = [
  "subnet-0daaf2be5dec61955",
  "subnet-03cf136be2c46758f",
  "subnet-00296dad4bb737a9c",
  "subnet-05736da0aa27f764c",
  "subnet-01152931280a3349b",
  "subnet-035085b24a26c10f6"
]
route_table_ids = [
  "rtb-09ea404613565894b"
]
security_group_id   = "sg-090f7897ebf5a7592"
image_uri           = "219040782795.dkr.ecr.us-east-1.amazonaws.com/successfulsuccess-backend@sha256:93c890e952725e557da209780b9f8642236dfd2d34a8c404a86e9aef8e257b05"
ai_image_uri        = "219040782795.dkr.ecr.us-east-1.amazonaws.com/successfulsuccess-backend@sha256:aacf83767bd41115f978ce98affabf493a3aa095756af59e2e0de88dfc2f0940"
architecture        = "arm64"
app_timezone        = "Europe/Kyiv"
sender_email        = "zhuraiev.pn@ucu.edu.ua"
recipient_emails    = "zhuraiev.pn@ucu.edu.ua"
schedule_expression = "cron(0 7 ? * MON *)"
allowed_origins     = "https://d27q0dddnqlp0w.cloudfront.net"
parser_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
bedrock_region      = "us-east-1"
callback_urls = [
  "http://localhost:3000/auth/callback/",
  "https://d27q0dddnqlp0w.cloudfront.net/auth/callback/"
]
logout_urls = [
  "http://localhost:3000/auth/callback/",
  "https://d27q0dddnqlp0w.cloudfront.net/auth/callback/"
]
