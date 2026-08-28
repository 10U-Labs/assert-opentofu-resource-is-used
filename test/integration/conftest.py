"""Integration test configuration."""

from __future__ import annotations

from test.samples import (
    ATTACHING,
    BLANK_NAME,
    COMMENTED,
    DETACHED,
    EXPORTED,
    HASH_COMMENT,
    HEREDOC,
    LISTED,
    PARAMETER,
    PARAMETER_READER,
    REMOTE_STATE_READER,
    SELF_NAMING,
    SPANNING_COMMENT,
    STRAY,
    TERRAFORM_OUTPUT_READER,
    UNBALANCED,
    VALUED,
    WORKFLOW_READER,
)
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LOCALS = """locals {
  prefix = "TenU"
  domain = "10ulabs.com"
}
"""

MODULE = """module "docs" {
  source = "../../../lib/terraform/docs"
}

resource "aws_s3_object" "index" {
  bucket = module.docs.bucket_id
  key    = "index.html"
}
"""

UNLABELLED_OUTPUT = """output {
  value = aws_dynamodb_table.audit.name
}
"""


def renamed(text: str, suffix: str) -> str:
    """Give one of the comment samples a name of its own.

    Args:
        text: The sample to rename.
        suffix: What to add to the resource name and to the deployed name.

    Returns:
        The sample, with nothing in it spelled the same as in its siblings.
    """
    return text.replace('"kept"', f'"kept_{suffix}"').replace("}Kept", f"}}Kept{suffix.title()}")


REPOSITORY = {
    "src/api/routing/locals.tf": LOCALS,
    "src/api/routing/db.tf": DETACHED,
    "src/api/routing/outputs.tf": EXPORTED,
    "src/api/routing/permission.tf": ATTACHING,
    "src/api/routing/function.tf": HEREDOC,
    "src/api/routing/docs.tf": MODULE,
    "src/api/routing/README.md": "The routing subsystem.\n",
    "src/api/exported/locals.tf": LOCALS,
    "src/api/exported/db.tf": DETACHED,
    "src/api/exported/outputs.tf": EXPORTED,
    "src/api/contact/locals.tf": LOCALS,
    "src/api/contact/contact.tf": VALUED,
    "src/api/other/main.tf": REMOTE_STATE_READER,
    "src/bootstrap/ssm.tf": PARAMETER,
    "test/api/conftest.py": TERRAFORM_OUTPUT_READER,
    "scripts/token.py": PARAMETER_READER,
    ".github/workflows/routing.yml": WORKFLOW_READER,
}

ODDITIES = {
    "odd/quirks/blank.tf": BLANK_NAME,
    "odd/quirks/circular.tf": SELF_NAMING,
    "odd/quirks/db.tf": DETACHED,
    "odd/quirks/hashed.tf": renamed(HASH_COMMENT, "hashed"),
    "odd/quirks/listed.tf": LISTED,
    "odd/quirks/quoted.tf": renamed(COMMENTED, "quoted"),
    "odd/quirks/spanning.tf": renamed(SPANNING_COMMENT, "spanning"),
    "odd/quirks/torn.tf": UNBALANCED,
    "odd/stray/db.tf": DETACHED,
    "odd/stray/stray.tf": STRAY,
    "odd/unlabelled/db.tf": DETACHED,
    "odd/unlabelled/outputs.tf": UNLABELLED_OUTPUT,
}


@pytest.fixture
def repository(write_tree: Callable[[dict[str, str]], Path]) -> Path:
    """Build a repository of several subsystems and the readers of their outputs.

    Returns:
        The repository root, entered so that every path below is relative.
    """
    return write_tree(REPOSITORY)


@pytest.fixture
def oddities(write_tree: Callable[[dict[str, str]], Path]) -> Path:
    """Build the directories of shapes a reader of OpenTofu text has to survive.

    Returns:
        The repository root, entered so that every path below is relative.
    """
    return write_tree(ODDITIES)


@pytest.fixture
def unreadable(tmp_path: Path) -> Path:
    """Build a directory holding one .tf file that is not text.

    Returns:
        The directory, which no run can judge.
    """
    (tmp_path / "binary.tf").write_bytes(b"\xff\xfe\x00")
    return tmp_path
