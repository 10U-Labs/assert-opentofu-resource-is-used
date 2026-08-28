"""End-to-end tests running the installed command the way a workflow step does."""

from __future__ import annotations

from test.samples import (
    DETACHED,
    EXPORTED,
    PARAMETER,
    PARAMETER_READER,
    REMOTE_STATE_READER,
    VALUED,
)
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    RunCli = Callable[[list[str]], tuple[int, str, str]]
    WriteTree = Callable[[dict[str, str]], Path]

DETACHED_TREE = {"src/routing/db.tf": DETACHED, "src/routing/outputs.tf": EXPORTED}

READ_TREE = {**DETACHED_TREE, "src/other/main.tf": REMOTE_STATE_READER}

REACHED_TREE = {"src/bootstrap/ssm.tf": PARAMETER, "scripts/token.py": PARAMETER_READER}

VALUED_TREE = {"src/contact/contact.tf": VALUED}

RUN = ["src/routing", "--search-in", "."]


@pytest.mark.e2e
class TestTheCommandAsAStepRunsIt:
    """The command as a workflow step invokes it."""

    def test_a_detached_resource_fails_the_step(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """Something found fails the run."""
        write_tree(DETACHED_TREE)
        assert run_cli_subprocess(RUN)[0] == 1

    def test_a_read_output_passes_the_step(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """Nothing found is success."""
        write_tree(READ_TREE)
        assert run_cli_subprocess(RUN)[0] == 0

    def test_names_the_file_to_open(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """The output names the file the resource is declared in."""
        write_tree(DETACHED_TREE)
        assert "src/routing/db.tf" in run_cli_subprocess(RUN)[1]

    def test_names_the_resource(self, write_tree: WriteTree, run_cli_subprocess: RunCli) -> None:
        """The output names the address to delete or attach."""
        write_tree(DETACHED_TREE)
        assert "aws_dynamodb_table.audit" in run_cli_subprocess(RUN)[1]

    def test_says_what_to_do_about_it(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """The message is the instruction rather than only the finding."""
        write_tree(DETACHED_TREE)
        assert "attach it or delete it" in run_cli_subprocess(RUN)[1]

    def test_annotates_for_the_diff(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """The annotation is what puts the finding on the line in the diff."""
        write_tree(DETACHED_TREE)
        assert "::error file=src/routing/db.tf,line=1::" in run_cli_subprocess(
            [*RUN, "--annotate"]
        )[1]

    def test_credits_a_program_that_names_the_identifier(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """A parameter read by name from a script is reached."""
        write_tree(REACHED_TREE)
        assert run_cli_subprocess(["src/bootstrap", "--search-in", "."])[0] == 0

    def test_credits_an_address_spelled_again(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """An identity a policy spells is what makes the policy work."""
        write_tree(VALUED_TREE)
        assert run_cli_subprocess(["src/contact"])[0] == 0

    def test_a_missing_directory_exits_two(
        self, write_tree: WriteTree, run_cli_subprocess: RunCli
    ) -> None:
        """A run with nothing to read is an error rather than a pass."""
        write_tree(DETACHED_TREE)
        assert run_cli_subprocess(["src/absent"])[0] == 2

    def test_the_help_names_the_search_flag(self, run_cli_subprocess: RunCli) -> None:
        """The flag a workflow needs is documented where it is looked for."""
        assert "--search-in" in run_cli_subprocess(["--help"])[1]
