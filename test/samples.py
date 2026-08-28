"""Sample OpenTofu directories the suites below read."""

DETACHED = """resource "aws_dynamodb_table" "audit" {
  name         = "${local.prefix}AuditTrail"
  billing_mode = "PAY_PER_REQUEST"
}
"""

EXPORTED = """output "audit_table_name" {
  value = aws_dynamodb_table.audit.name
}
"""

ADDRESSED = """resource "aws_lambda_function" "handler" {
  function_name = "${local.prefix}Handler"
  environment {
    variables = {
      TABLE = aws_dynamodb_table.audit.name
    }
  }
}
"""

ATTACHING = """resource "aws_lambda_permission" "invoke" {
  statement_id = "AllowGateway"
  function_name = aws_dynamodb_table.audit.name
}
"""

VALUED = """resource "aws_ses_email_identity" "contact" {
  email = "contact@${local.domain}"
}

resource "aws_lambda_function" "mailer" {
  function_name = "${local.prefix}Mailer"
  role          = aws_iam_role.mailer.arn
  environment {
    variables = {
      CONTACT_EMAIL = "contact@${local.domain}"
    }
  }
}

resource "aws_iam_role" "mailer" {
  name = "${local.prefix}MailerRole"
}
"""

PARAMETER = """resource "aws_ssm_parameter" "token" {
  name  = "/10u/github-token"
  type  = "SecureString"
  value = "unset"
}
"""

REMOTE_STATE_READER = """data "terraform_remote_state" "routing" {
  backend = "s3"
}

resource "aws_iam_role" "other" {
  name = data.terraform_remote_state.routing.outputs.audit_table_name
}
"""

TERRAFORM_OUTPUT_READER = """from lib import terraform_output


def table() -> str:
    return terraform_output(ROUTING_DIR, "audit_table_name")
"""

WORKFLOW_READER = """jobs:
  reconciliation:
    steps:
      - run: terraform output -raw audit_table_name
"""

PARAMETER_READER = """import boto3


def token() -> str:
    return boto3.client("ssm").get_parameter(Name="/10u/github-token")
"""

HEREDOC = """resource "aws_cloudfront_function" "rewrite" {
  name = "RootUrlRewrite"
  code = <<-EOT
resource "aws_dynamodb_table" "audit" {
  var = { unbalanced
}
echo ${aws_dynamodb_table.audit.name}
EOT
}
"""

COMMENTED = '''resource "aws_iam_role" "kept" {
  /* aws_dynamodb_table.audit */
  name = "${local.prefix}Kept"
}
'''

SPANNING_COMMENT = '''resource "aws_iam_role" "kept" {
  /* the table
     aws_dynamodb_table.audit
     is named here only */ name = "${local.prefix}Kept"
}
'''

HASH_COMMENT = '''resource "aws_iam_role" "kept" {
  # aws_dynamodb_table.audit
  name = "${local.prefix}Kept"
}
'''

UNBALANCED = """resource "aws_iam_role" "torn" {
  name = "${local.prefix}Torn"
"""

STRAY = """aws_dynamodb_table.audit
"""

BLANK_NAME = '''resource "aws_iam_role" "blank" {
  name = ""
}
'''

LISTED = '''resource "aws_iam_policy" "listed" {
  name = "${local.prefix}Listed"
  actions = [
    "s3:GetObject",
  ]
}
'''

SELF_NAMING = """resource "aws_iam_role" "circular" {
  name        = "${local.prefix}Circular"
  description = "${aws_iam_role.circular.id}"
}
"""
