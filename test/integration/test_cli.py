"""Integration tests driving the CLI over repositories on disk."""

from __future__ import annotations

import runpy
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from assert_opentofu_resource_is_used.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_SUCCESS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    RunCli = Callable[[list[str]], tuple[int, str, str]]

EXPORTED = "src/api/exported"
ROUTING = "src/api/routing"

SUBSYSTEMS = [
    ROUTING,
    EXPORTED,
    "src/api/contact",
    "src/api/other",
    "src/bootstrap",
]


@pytest.mark.integration
@pytest.mark.usefixtures("repository")
class TestSubsystems:
    """Tests over a repository of several subsystems and the readers of them."""

    def test_a_wired_subsystem_passes_alone(self, run_cli: RunCli) -> None:
        """A subsystem whose resources reach each other needs no search tree."""
        assert run_cli([ROUTING])[0] == EXIT_SUCCESS

    def test_an_exporting_subsystem_fails_alone(self, run_cli: RunCli) -> None:
        """Exporting a table is not using it while nothing reads the output."""
        assert run_cli([EXPORTED])[0] == EXIT_FINDINGS

    def test_the_refusal_names_the_resource(self, run_cli: RunCli) -> None:
        """The finding says which resource is reached by nothing."""
        assert "aws_dynamodb_table.audit" in run_cli([EXPORTED])[1]

    def test_a_read_output_saves_the_subsystem(self, run_cli: RunCli) -> None:
        """Another subsystem, a test and a workflow all read that output."""
        assert run_cli([EXPORTED, "--search-in", "."])[0] == EXIT_SUCCESS

    def test_one_file_is_search_tree_enough(self, run_cli: RunCli) -> None:
        """The conftest calling terraform_output is the whole credit."""
        assert run_cli([EXPORTED, "--search-in", "test/api/conftest.py"])[0] == EXIT_SUCCESS

    def test_attachment_by_value_saves_an_identity(self, run_cli: RunCli) -> None:
        """An address spelled again in a policy is what makes the policy work."""
        assert run_cli(["src/api/contact"])[0] == EXIT_SUCCESS

    def test_a_parameter_fails_without_its_reader(self, run_cli: RunCli) -> None:
        """Nothing in the bootstrap's own OpenTofu reaches the parameter."""
        assert run_cli(["src/bootstrap"])[0] == EXIT_FINDINGS

    def test_a_script_naming_a_parameter_saves_it(self, run_cli: RunCli) -> None:
        """A parameter read by name from Python is reached."""
        assert run_cli(["src/bootstrap", "--search-in", "scripts"])[0] == EXIT_SUCCESS

    def test_the_whole_repository_passes(self, run_cli: RunCli) -> None:
        """Every subsystem at once, crediting a use from anywhere, is clean."""
        assert run_cli([*SUBSYSTEMS, "--search-in", "."])[0] == EXIT_SUCCESS

    def test_prose_beside_the_source_is_not_read(self, run_cli: RunCli) -> None:
        """A README in the subsystem is neither OpenTofu nor a program."""
        assert "README" not in run_cli([ROUTING, "--verbose"])[1]

    def test_the_resources_read_are_reported(self, run_cli: RunCli) -> None:
        """A verbose run says how many resources it looked at."""
        assert "Resources read: 4" in run_cli([ROUTING, "--verbose"])[1]

    def test_the_directories_read_are_reported(self, run_cli: RunCli) -> None:
        """A verbose run says how many directories it was given."""
        assert "Reading 5 directory(s)" in run_cli([*SUBSYSTEMS, "--verbose"])[1]


@pytest.mark.integration
@pytest.mark.usefixtures("repository")
class TestOptions:
    """Tests for the flags a workflow step passes."""

    def test_annotating_lands_on_the_line(self, run_cli: RunCli) -> None:
        """An annotation names the file and the line the resource opens on."""
        assert "::error file=src/api/exported/db.tf,line=1::" in run_cli(
            [EXPORTED, "--annotate"]
        )[1]

    def test_counting_prints_the_number(self, run_cli: RunCli) -> None:
        """Counting prints how many were refused and nothing else."""
        assert run_cli([EXPORTED, "--count"])[1] == "1\n"

    def test_quiet_prints_nothing(self, run_cli: RunCli) -> None:
        """A quiet run reports through its exit code alone."""
        assert run_cli([EXPORTED, "--quiet"])[1] == ""

    def test_warn_only_still_exits_zero(self, run_cli: RunCli) -> None:
        """A warning run reports without failing the step."""
        assert run_cli([EXPORTED, "--warn-only"])[0] == EXIT_SUCCESS

    def test_an_excluded_file_is_not_read(self, run_cli: RunCli) -> None:
        """A resource in an excluded file is not there to refuse."""
        assert run_cli([EXPORTED, "--exclude", "db.tf"])[0] == EXIT_SUCCESS

    def test_the_excludes_are_reported(self, run_cli: RunCli) -> None:
        """A verbose run says what it was told to leave out, blanks dropped."""
        assert "Excluding patterns: db.tf, *.json" in run_cli(
            [EXPORTED, "--verbose", "--exclude", "db.tf, ,*.json"]
        )[1]

    def test_two_output_modes_are_a_usage_error(self, run_cli: RunCli) -> None:
        """Quiet and verbose together is a usage error."""
        assert run_cli([EXPORTED, "--quiet", "--verbose"])[0] == EXIT_ERROR


@pytest.mark.integration
@pytest.mark.usefixtures("oddities")
class TestOddities:
    """Tests for the shapes a reader of OpenTofu text has to survive."""

    def test_every_detached_resource_is_refused(self, run_cli: RunCli) -> None:
        """The directory of quirks holds eight resources and no use at all."""
        assert run_cli(["odd/quirks", "--count"])[1] == "8\n"

    def test_fail_fast_stops_at_the_first(self, run_cli: RunCli) -> None:
        """One refusal is enough to stop looking."""
        assert run_cli(["odd/quirks", "--count", "--fail-fast"])[1] == "1\n"

    def test_a_hash_comment_credits_nothing(self, run_cli: RunCli) -> None:
        """A resource named only behind a hash is named by nothing."""
        assert "aws_dynamodb_table.audit" in run_cli(["odd/quirks"])[1]

    def test_a_block_comment_is_not_code(self, run_cli: RunCli) -> None:
        """The role whose only content is a commented reference is refused."""
        assert "aws_iam_role.kept_quoted" in run_cli(["odd/quirks"])[1]

    def test_a_comment_spanning_lines_is_not_code(self, run_cli: RunCli) -> None:
        """A block comment closing on a later line hides what it holds."""
        assert "aws_iam_role.kept_spanning" in run_cli(["odd/quirks"])[1]

    def test_an_unclosed_block_is_still_read(self, run_cli: RunCli) -> None:
        """A resource whose braces never balance ends where the file does."""
        assert "aws_iam_role.torn" in run_cli(["odd/quirks"])[1]

    def test_a_reference_in_no_block_is_a_use(self, run_cli: RunCli) -> None:
        """Text belonging to no block is credited on sight."""
        assert run_cli(["odd/stray"])[0] == EXIT_SUCCESS

    def test_an_output_with_no_name_publishes_nothing(self, run_cli: RunCli) -> None:
        """Nothing can read an output nothing can address."""
        assert run_cli(["odd/unlabelled"])[0] == EXIT_FINDINGS


@pytest.mark.integration
class TestFailures:
    """Tests for what a run does with what it cannot read."""

    def test_a_missing_directory_is_fatal(self, run_cli: RunCli) -> None:
        """A run with nothing to read is an error rather than a pass."""
        assert run_cli(["absent"])[0] == EXIT_ERROR

    @pytest.mark.usefixtures("repository")
    def test_a_missing_directory_is_named(self, run_cli: RunCli) -> None:
        """The directory that is not there is named on standard error."""
        assert "absent" in run_cli([ROUTING, "absent"])[2]

    def test_an_unreadable_search_file_is_survived(
        self, repository: Path, run_cli: RunCli
    ) -> None:
        """One unreadable program does not stop the rest crediting a use."""
        (repository / "scripts/binary.py").write_bytes(b"\xff\xfe\x00")
        assert "aws_ssm_parameter.token" not in run_cli(["src/bootstrap", "--search-in", "."])[1]

    def test_an_unreadable_subsystem_file_is_an_error(
        self, unreadable: Path, run_cli: RunCli
    ) -> None:
        """A .tf file that is not text stops the directory being judged."""
        assert run_cli([str(unreadable)])[0] == EXIT_ERROR

    def test_an_unreadable_file_is_reported(self, unreadable: Path, run_cli: RunCli) -> None:
        """A verbose run says that something would not read."""
        assert "Errors occurred during scanning." in run_cli([str(unreadable), "--verbose"])[1]


def run_as_a_module(arguments: list[str]) -> int:
    """Run the package the way a workflow step does and report what it exits with.

    Args:
        arguments: What to put on the command line after the program name.

    Returns:
        The exit code the run asked for.
    """
    sys.modules.pop("assert_opentofu_resource_is_used.__main__", None)
    with patch.object(sys, "argv", ["assert-opentofu-resource-is-used", *arguments]):
        try:
            runpy.run_module("assert_opentofu_resource_is_used", run_name="__main__")
        except SystemExit as exit_request:
            return int(exit_request.code) if exit_request.code is not None else 0
    return 0


@pytest.mark.integration
@pytest.mark.usefixtures("repository")
class TestModule:
    """Tests for running the package the way a workflow step does."""

    def test_running_as_a_module_reports_the_finding(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """python -m reaches the same CLI as the console script."""
        run_as_a_module([EXPORTED])
        assert "aws_dynamodb_table.audit" in capsys.readouterr().out

    def test_running_as_a_module_fails_the_step(self) -> None:
        """The exit code a step reads is the same one either way."""
        assert run_as_a_module([EXPORTED]) == EXIT_FINDINGS
