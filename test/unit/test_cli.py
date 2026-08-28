"""Unit tests for the command-line interface."""

from __future__ import annotations

from test.samples import (
    ADDRESSED,
    DETACHED,
    EXPORTED,
    PARAMETER,
    PARAMETER_READER,
    REMOTE_STATE_READER,
    TERRAFORM_OUTPUT_READER,
    WORKFLOW_READER,
)
from typing import TYPE_CHECKING

import pytest

from assert_opentofu_resource_is_used.cli import (
    EXIT_ERROR,
    EXIT_FINDINGS,
    EXIT_SUCCESS,
    Options,
    ScanResult,
    build_corpus,
    create_parser,
    determine_exit_code,
    output_findings,
    parse_patterns,
    present,
    read_directory,
    read_file,
    should_skip,
    terraform_files,
    walk_files,
)
from assert_opentofu_resource_is_used.scanner import Corpus, Finding

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FINDING = Finding("src/db.tf", 1, "aws_dynamodb_table.audit")

TREE = {
    "src/db.tf": DETACHED,
    "src/outputs.tf": EXPORTED,
    "src/notes.md": "the table",
    "other/main.tf": REMOTE_STATE_READER,
    "test/conftest.py": TERRAFORM_OUTPUT_READER,
    ".github/workflows/deploy.yml": WORKFLOW_READER,
    "scripts/deploy.sh": "aws dynamodb list-tables\n",
}


@pytest.mark.unit
class TestParsing:
    """Tests for reading the command line."""

    def test_a_directory_is_required(self) -> None:
        """The parser refuses a run with no directory to check."""
        with pytest.raises(SystemExit):
            create_parser().parse_args([])

    def test_search_in_repeats(self) -> None:
        """Every search tree given is kept."""
        parsed = create_parser().parse_args(["src", "--search-in", "a", "--search-in", "b"])
        assert parsed.search_in == ["a", "b"]

    def test_search_in_defaults_to_nothing(self) -> None:
        """Without the flag there is nothing to fall back from."""
        assert create_parser().parse_args(["src"]).search_in is None

    def test_quiet_and_verbose_are_exclusive(self) -> None:
        """Two output modes at once is a usage error."""
        with pytest.raises(SystemExit):
            create_parser().parse_args(["src", "--quiet", "--verbose"])

    def test_no_patterns_is_no_list(self) -> None:
        """An absent exclude leaves nothing to match."""
        assert parse_patterns(None) == []

    def test_blank_patterns_are_dropped(self) -> None:
        """A trailing comma names no pattern."""
        assert parse_patterns("a, ,b") == ["a", "b"]

    def test_a_pattern_matches_a_basename(self) -> None:
        """A pattern naming a file matches it wherever it sits."""
        assert should_skip("src/generated.tf", ["generated.tf"])

    def test_a_pattern_that_matches_nothing_skips_nothing(self) -> None:
        """A file no pattern names is read."""
        assert not should_skip("src/db.tf", ["generated.tf"])


@pytest.mark.unit
class TestCollecting:
    """Tests for choosing the files to read."""

    def test_only_terraform_is_read_from_a_directory(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """A directory argument gives up its .tf files and nothing else."""
        write_tree(TREE)
        assert terraform_files("src", []) == ["src/db.tf", "src/outputs.tf"]

    def test_a_directory_below_is_not_read(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """A module directory beneath a subsystem is a namespace of its own."""
        write_tree({"src/db.tf": DETACHED, "src/modules/inner/main.tf": ADDRESSED})
        assert terraform_files("src", []) == ["src/db.tf"]

    def test_an_excluded_file_is_left_out(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """A pattern keeps a file out of the directory."""
        write_tree(TREE)
        assert terraform_files("src", ["outputs.tf"]) == ["src/db.tf"]

    def test_a_search_tree_gives_up_every_suffix(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """The five program suffixes and OpenTofu itself are searched."""
        write_tree(TREE)
        assert len(walk_files(".", [])) == 6

    def test_a_search_tree_leaves_out_prose(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """A markdown file credits nothing and is not read."""
        write_tree(TREE)
        assert not [path for path in walk_files(".", []) if path.endswith(".md")]

    def test_a_single_file_is_a_search_tree(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """One file named on its own is searched."""
        write_tree(TREE)
        assert walk_files("other/main.tf", []) == ["other/main.tf"]

    def test_a_vendored_directory_is_skipped(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """A .terraform directory holds another copy of everything."""
        write_tree({"src/db.tf": DETACHED, "src/.terraform/modules/x/main.tf": ADDRESSED})
        assert walk_files(".", []) == ["src/db.tf"]


@pytest.mark.unit
class TestReading:
    """Tests for reading files off the disk."""

    def test_a_file_that_will_not_decode_is_an_error(self, tmp_path: Path) -> None:
        """A file that is not text cannot be read."""
        binary = tmp_path / "binary.tf"
        binary.write_bytes(b"\xff\xfe\x00")
        result = ScanResult()
        read_file(str(binary), result)
        assert result.had_error

    def test_a_file_that_will_not_decode_reads_as_nothing(self, tmp_path: Path) -> None:
        """Nothing comes back from a file that cannot be read."""
        binary = tmp_path / "binary.tf"
        binary.write_bytes(b"\xff\xfe\x00")
        assert read_file(str(binary), ScanResult()) is None

    def test_a_missing_file_is_an_error(self, tmp_path: Path) -> None:
        """A path naming nothing cannot be read."""
        result = ScanResult()
        read_file(str(tmp_path / "absent.tf"), result)
        assert result.had_error

    def test_a_corpus_groups_terraform(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """The OpenTofu of the whole repository is one text."""
        write_tree(TREE)
        assert "terraform_remote_state" in build_corpus(["."], [], ScanResult()).terraform

    def test_a_corpus_groups_python(self, write_tree: Callable[[dict[str, str]], Path]) -> None:
        """The Python of the whole repository is one text."""
        write_tree(TREE)
        assert "terraform_output" in build_corpus(["."], [], ScanResult()).python

    def test_a_corpus_groups_workflows(self, write_tree: Callable[[dict[str, str]], Path]) -> None:
        """The workflow files of the whole repository are one text."""
        write_tree(TREE)
        assert "output -raw" in build_corpus(["."], [], ScanResult()).workflows

    def test_a_corpus_groups_programs(self, write_tree: Callable[[dict[str, str]], Path]) -> None:
        """A shell script is a program a resource can be reached from."""
        write_tree(TREE)
        assert "list-tables" in build_corpus(["."], [], ScanResult()).programs

    def test_a_corpus_survives_a_file_it_cannot_read(self, tmp_path: Path) -> None:
        """One unreadable file does not stop the rest being searched."""
        (tmp_path / "good.py").write_text(PARAMETER_READER, encoding="utf-8")
        (tmp_path / "bad.py").write_bytes(b"\xff\xfe\x00")
        assert "github-token" in build_corpus([str(tmp_path)], [], ScanResult()).programs

    def test_a_directory_it_cannot_read_is_an_error(self, tmp_path: Path) -> None:
        """An unreadable .tf file makes the run an error."""
        (tmp_path / "bad.tf").write_bytes(b"\xff\xfe\x00")
        result = ScanResult()
        read_directory(str(tmp_path), Corpus(), result, Options())
        assert result.had_error

    def test_the_resources_read_are_counted(
        self, write_tree: Callable[[dict[str, str]], Path]
    ) -> None:
        """A run reports how many resources it looked at."""
        write_tree(TREE)
        result = ScanResult()
        read_directory("src", Corpus(), result, Options())
        assert result.resources_read == 1

    def test_reading_can_be_narrated(
        self, write_tree: Callable[[dict[str, str]], Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A verbose run names each file as it opens it."""
        write_tree(TREE)
        read_directory("src", Corpus(), ScanResult(), Options(verbose=True))
        assert "Reading: src/db.tf" in capsys.readouterr().out


@pytest.mark.unit
class TestReporting:
    """Tests for what a run prints and what it exits with."""

    def test_a_finding_is_printed_with_its_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A plain run prints the finding and why it is one."""
        output_findings([FINDING])
        assert capsys.readouterr().out.startswith("src/db.tf:1:aws_dynamodb_table.audit: is ")

    def test_counting_prints_only_the_number(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Counting prints how many there were and nothing else."""
        output_findings([FINDING], count_mode=True)
        assert capsys.readouterr().out == "1\n"

    def test_annotating_names_the_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An annotation lands on the line the finding names."""
        output_findings([FINDING], annotate=True)
        assert capsys.readouterr().out.startswith("::error file=src/db.tf,line=1::")

    def test_findings_exit_one(self) -> None:
        """A run with findings fails."""
        assert determine_exit_code(ScanResult(findings=[FINDING])) == EXIT_FINDINGS

    def test_warn_only_exits_zero(self) -> None:
        """A warning run always succeeds."""
        assert determine_exit_code(ScanResult(findings=[FINDING]), warn_only=True) == EXIT_SUCCESS

    def test_an_error_exits_two(self) -> None:
        """A run that could not read something is an error."""
        assert determine_exit_code(ScanResult(had_error=True)) == EXIT_ERROR

    def test_a_clean_run_exits_zero(self) -> None:
        """A run with nothing to report succeeds."""
        assert determine_exit_code(ScanResult()) == EXIT_SUCCESS

    def test_a_missing_directory_is_reported(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A directory that is not there is named on standard error."""
        present(["absent"], ScanResult())
        assert "Error: Directory not found: absent" in capsys.readouterr().err

    def test_a_missing_directory_is_dropped(self) -> None:
        """Only the directories that exist are read."""
        assert not present(["absent"], ScanResult())


@pytest.mark.unit
class TestRunning:
    """Tests for driving the whole CLI."""

    def test_a_detached_resource_fails_the_run(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """A subsystem holding a resource nothing reaches is refused."""
        write_tree({"src/db.tf": DETACHED})
        assert run_cli(["src"])[0] == EXIT_FINDINGS

    def test_a_read_export_passes_the_run(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """The same subsystem passes once another one reads its output."""
        write_tree(TREE)
        assert run_cli(["src", "--search-in", "."])[0] == EXIT_SUCCESS

    def test_a_parameter_named_by_a_program_passes(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """A resource reached from outside OpenTofu is reached."""
        write_tree({"src/ssm.tf": PARAMETER, "scripts/token.py": PARAMETER_READER})
        assert run_cli(["src", "--search-in", "."])[0] == EXIT_SUCCESS

    def test_two_directories_are_both_read(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """Every directory named is checked."""
        write_tree({"one/db.tf": DETACHED, "two/db.tf": DETACHED})
        assert run_cli(["one", "two", "--count"])[1] == "2\n"

    def test_fail_fast_stops_at_the_first(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """One finding is enough to stop looking."""
        write_tree({"one/db.tf": DETACHED, "two/db.tf": DETACHED})
        assert run_cli(["one", "two", "--count", "--fail-fast"])[1] == "1\n"

    def test_quiet_prints_nothing(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """A quiet run reports through its exit code alone."""
        write_tree({"src/db.tf": DETACHED})
        assert run_cli(["src", "--quiet"])[1] == ""

    def test_verbose_summarises(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """A verbose run ends with what it read and what it found."""
        write_tree({"src/db.tf": DETACHED})
        assert "Resources read: 1" in run_cli(["src", "--verbose"])[1]

    def test_verbose_names_the_excludes(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """A verbose run says what it was told to leave out."""
        write_tree({"src/db.tf": DETACHED})
        assert "Excluding patterns: outputs.tf" in run_cli(
            ["src", "--verbose", "--exclude", "outputs.tf"]
        )[1]

    def test_verbose_reports_an_error(
        self,
        run_cli: Callable[[list[str]], tuple[int, str, str]],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A verbose run says when something would not read."""
        (tmp_path / "bad.tf").write_bytes(b"\xff\xfe\x00")
        monkeypatch.chdir(tmp_path)
        assert "Errors occurred" in run_cli([".", "--verbose"])[1]

    def test_every_directory_missing_is_fatal(
        self, run_cli: Callable[[list[str]], tuple[int, str, str]]
    ) -> None:
        """A run with nothing to read is an error rather than a pass."""
        assert run_cli(["absent"])[0] == EXIT_ERROR

    def test_warn_only_reports_without_failing(
        self,
        write_tree: Callable[[dict[str, str]], Path],
        run_cli: Callable[[list[str]], tuple[int, str, str]],
    ) -> None:
        """A warning run still prints what it found."""
        write_tree({"src/db.tf": DETACHED})
        assert run_cli(["src", "--warn-only"])[0] == EXIT_SUCCESS
