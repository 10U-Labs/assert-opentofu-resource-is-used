"""Command-line interface for assert-opentofu-resource-is-used."""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .scanner import Corpus, Finding, detached_resources, read_source

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_SUCCESS = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

SKIPPED_DIRECTORIES = (".git", ".terraform", "__pycache__", "node_modules")

TERRAFORM = ".tf"
PYTHON = ".py"
WORKFLOW = ".yml"
PROGRAM_SUFFIXES = (".py", ".yml", ".sh", ".js", ".ts")
SEARCHED_SUFFIXES = (".tf", ".py", ".yml", ".sh", ".js", ".ts")

MESSAGE = (
    "is interpolated by nothing, interpolates nothing, repeats no string and "
    "is named by no program; attach it or delete it"
)


@dataclass(frozen=True)
class Options:
    """What a run was asked to leave out, and whether to narrate it."""

    exclude: list[str] = field(default_factory=list)
    verbose: bool = False


@dataclass
class ScanResult:
    """The outcome of one run over a set of directories."""

    findings: list[Finding] = field(default_factory=list)
    resources_read: int = 0
    files_scanned: int = 0
    had_error: bool = False


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="assert-opentofu-resource-is-used",
        description=(
            "Assert that every OpenTofu resource in the given directories is reached by "
            "something. A resource nothing references, nothing reaches by value and no "
            "program names by its deployed identifier is applied on every deployment and "
            "does nothing, and both tofu validate and tflint accept it."
        ),
    )

    parser.add_argument(
        "directories",
        nargs="+",
        metavar="DIRECTORY",
        help=(
            "One or more subsystem directories holding the resources to check. Each is "
            "read for the *.tf files directly in it, since a module directory beneath "
            "one is a namespace of its own."
        ),
    )

    parser.add_argument(
        "--search-in",
        action="append",
        default=None,
        metavar="PATH",
        dest="search_in",
        help=(
            "A tree to credit a use from, repeatable. Defaults to the directories "
            "themselves, so pass the whole repository: a remote state reader lives in "
            "another subsystem, a terraform_output call under the tests and a "
            "terraform output -raw step in a workflow."
        ),
    )

    parser.add_argument(
        "--exclude",
        metavar="PATTERNS",
        help="Comma-separated glob patterns to leave out of both the directories and the search.",
    )

    parser.add_argument(
        "--annotate",
        action="store_true",
        help=(
            "Print each finding as a GitHub Actions ::error annotation, so it lands on "
            "the line it names in the diff."
        ),
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output. Exit code indicates success (0) or findings (1).",
    )
    output_group.add_argument(
        "--count",
        action="store_true",
        help="Output only the count of findings.",
    )
    output_group.add_argument(
        "--verbose",
        action="store_true",
        help="Show the directories read, the resources found, the findings and a summary.",
    )

    behavior_group = parser.add_mutually_exclusive_group()
    behavior_group.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit immediately after finding the first detached resource.",
    )
    behavior_group.add_argument(
        "--warn-only",
        action="store_true",
        help="Always exit with code 0, even if findings exist.",
    )

    return parser


def parse_patterns(patterns_str: str | None) -> list[str]:
    """Parse a comma-separated patterns string.

    Args:
        patterns_str: Comma-separated patterns, or None.

    Returns:
        The patterns, empty when the input is None or blank.
    """
    if not patterns_str:
        return []
    return [pattern.strip() for pattern in patterns_str.split(",") if pattern.strip()]


def should_skip(path: str, exclude_patterns: list[str]) -> bool:
    """Check whether a file matches any exclude pattern.

    Args:
        path: The file path to check.
        exclude_patterns: Glob patterns to exclude.

    Returns:
        True when the path or its basename matches a pattern.
    """
    return any(
        fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern)
        for pattern in exclude_patterns
    )


def terraform_files(directory: str, exclude_patterns: list[str]) -> list[str]:
    """List the .tf files directly in one directory.

    Args:
        directory: The directory to read.
        exclude_patterns: Glob patterns to exclude.

    Returns:
        The paths, sorted, and without the ones excluded.
    """
    entries = [os.path.join(directory, name) for name in sorted(os.listdir(directory))]
    return [
        path
        for path in entries
        if path.endswith(TERRAFORM)
        and os.path.isfile(path)
        and not should_skip(path, exclude_patterns)
    ]


def walk_files(tree: str, exclude_patterns: list[str]) -> list[str]:
    """Find every file under a tree whose suffix a use may be credited from.

    Args:
        tree: A file path or a directory path.
        exclude_patterns: Glob patterns to exclude.

    Returns:
        The paths, sorted and without repeats.
    """
    if os.path.isfile(tree):
        candidates = [tree]
    else:
        candidates = []
        for root, directories, filenames in os.walk(tree):
            directories[:] = [name for name in directories if name not in SKIPPED_DIRECTORIES]
            candidates.extend(os.path.join(root, filename) for filename in filenames)
    return sorted(
        {
            os.path.normpath(path)
            for path in candidates
            if path.endswith(SEARCHED_SUFFIXES) and not should_skip(path, exclude_patterns)
        }
    )


def read_file(path: str, result: ScanResult) -> str | None:
    """Read one file, recording an error on the result if it cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as error:
        print(f"Error reading {path}: {error}", file=sys.stderr)
        result.had_error = True
        return None


def build_corpus(trees: Sequence[str], exclude_patterns: list[str], result: ScanResult) -> Corpus:
    """Read every searched tree into the four texts the credits are looked up in.

    Args:
        trees: The trees a use may be credited from.
        exclude_patterns: Glob patterns to exclude.
        result: The result to record read errors on.

    Returns:
        The corpus, one string per kind of reader.
    """
    grouped: dict[str, list[str]] = {"terraform": [], "python": [], "workflows": [], "programs": []}
    for tree in trees:
        for path in walk_files(tree, exclude_patterns):
            content = read_file(path, result)
            if content is None:
                continue
            if path.endswith(TERRAFORM):
                grouped["terraform"].append(content)
            if path.endswith(PYTHON):
                grouped["python"].append(content)
            if path.endswith(WORKFLOW):
                grouped["workflows"].append(content)
            if path.endswith(PROGRAM_SUFFIXES):
                grouped["programs"].append(content)
    return Corpus(
        terraform="\n".join(grouped["terraform"]),
        python="\n".join(grouped["python"]),
        workflows="\n".join(grouped["workflows"]),
        programs="\n".join(grouped["programs"]),
    )


def read_directory(
    directory: str, corpus: Corpus, result: ScanResult, options: Options
) -> list[Finding]:
    """Read one subsystem directory and report the resources nothing reaches.

    Args:
        directory: The directory to read.
        corpus: The text a use may be credited from.
        result: The result to record read errors and counts on.
        options: The patterns to leave out and whether to name each file read.

    Returns:
        Every finding in that directory, in file and line order.
    """
    sources = []
    for path in terraform_files(directory, options.exclude):
        content = read_file(path, result)
        if content is None:
            continue
        if options.verbose:
            print(f"Reading: {path}")
        sources.append(read_source(path, content))
        result.files_scanned += 1
    result.resources_read += sum(
        1 for source in sources for block in source.blocks if block.kind == "resource"
    )
    return detached_resources(sources, corpus)


def output_findings(
    findings: list[Finding], count_mode: bool = False, annotate: bool = False
) -> None:
    """Print findings in the requested format.

    Args:
        findings: The findings to print.
        count_mode: Print only how many there are.
        annotate: Print each as a GitHub Actions ::error annotation.
    """
    if count_mode:
        print(len(findings))
        return
    for finding in findings:
        if annotate:
            print(
                f"::error file={finding.path},line={finding.line_number}::"
                f"{finding.address} {MESSAGE}"
            )
        else:
            print(f"{finding}: {MESSAGE}")


def determine_exit_code(result: ScanResult, warn_only: bool = False) -> int:
    """Choose the exit code for a result.

    Args:
        result: The scan result.
        warn_only: Always succeed when true.

    Returns:
        0 for success, 1 for findings, 2 for errors.
    """
    if warn_only:
        return EXIT_SUCCESS
    if result.findings:
        return EXIT_FINDINGS
    if result.had_error:
        return EXIT_ERROR
    return EXIT_SUCCESS


def report(result: ScanResult, args: argparse.Namespace) -> None:
    """Print whatever the chosen output mode asks for."""
    if args.quiet:
        return
    output_findings(result.findings, args.count, args.annotate)
    if args.verbose:
        print()
        print(f"Files scanned: {result.files_scanned}")
        print(f"Resources read: {result.resources_read}")
        print(f"Findings: {len(result.findings)}")
        if result.had_error:
            print("Errors occurred during scanning.")


def present(directories: Sequence[str], result: ScanResult) -> list[str]:
    """Keep the directories that exist, reporting the ones that do not.

    Args:
        directories: The directories named on the command line.
        result: The result to record the missing ones on.

    Returns:
        The directories that exist, in the order they were given.
    """
    found: list[str] = []
    for directory in directories:
        if os.path.isdir(directory):
            found.append(directory)
            continue
        print(f"Error: Directory not found: {directory}", file=sys.stderr)
        result.had_error = True
    return found


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI.

    Args:
        argv: Command-line arguments, defaulting to sys.argv[1:].
    """
    args = create_parser().parse_args(argv)
    exclude_patterns = parse_patterns(args.exclude)
    options = Options(exclude=exclude_patterns, verbose=args.verbose)
    result = ScanResult()

    directories = present(args.directories, result)
    if not directories:
        sys.exit(EXIT_ERROR)

    corpus = build_corpus(args.search_in or directories, exclude_patterns, result)
    if args.verbose:
        print(f"Reading {len(directories)} directory(s)...")
        if exclude_patterns:
            print(f"Excluding patterns: {', '.join(exclude_patterns)}")
        print()

    findings: list[Finding] = []
    for directory in directories:
        findings.extend(read_directory(directory, corpus, result, options))
    result.findings = findings[:1] if (args.fail_fast and findings) else findings

    report(result, args)
    sys.exit(determine_exit_code(result, args.warn_only))
