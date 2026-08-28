"""Core logic for finding OpenTofu resources nothing in their subsystem uses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

DATA = "data"
MODULE = "module"
OUTPUT = "output"
RESOURCE = "resource"

BLOCK_COMMENT = re.compile(r"/\*.*?\*/")
BLOCK_HEADER = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)((?:[ \t]+"[^"\n]*")*)[ \t]*\{', re.MULTILINE)
HEREDOC = re.compile(r"<<[-~]?([A-Za-z_][A-Za-z0-9_]*)")
INTERPOLATION = re.compile(r"\$\{[^{}]*\}")
LABEL = re.compile(r'"([^"\n]*)"')
LINE_COMMENT = re.compile(r"(?:#|//).*$")
OPEN_COMMENT = re.compile(r"/\*.*$")
STRING = re.compile(r'"(?:\\.|[^"\\\n])*"')
ASSIGNED = re.compile(r'^[ \t]*([A-Za-z_][A-Za-z0-9_-]*)[ \t]*=[ \t]*"((?:\\.|[^"\\\n])*)"[ \t]*$')

IDENTITY_ATTRIBUTES = (
    "alarm_name",
    "alias",
    "bucket",
    "domain_name",
    "email",
    "function_name",
    "group_name",
    "identifier",
    "key",
    "log_group_name",
    "name",
    "parameter_name",
    "policy_name",
    "queue_name",
    "repository_name",
    "role_name",
    "rule_name",
    "stage_name",
    "statement_id",
    "table_name",
    "topic_name",
    "trail_name",
    "user_name",
    "vault_name",
)

OPENERS = "{["
CLOSERS = "}]"


@dataclass(frozen=True)
class Finding:
    """A resource nothing in its subsystem and nothing outside OpenTofu reaches."""

    path: str
    line_number: int
    address: str

    def __str__(self) -> str:
        """Format as path:line:address."""
        return f"{self.path}:{self.line_number}:{self.address}"


@dataclass(frozen=True)
class Block:
    """One top-level block of an OpenTofu file, with the span its braces enclose."""

    path: str
    line_number: int
    kind: str
    labels: tuple[str, ...]
    opening: int
    end: int


@dataclass(frozen=True)
class Source:
    """One .tf file, read twice over and split into the blocks it declares."""

    path: str
    text: str
    structure: str
    uncommented: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Corpus:
    """The text a use may be credited from, grouped by how each kind is read."""

    terraform: str = ""
    python: str = ""
    workflows: str = ""
    programs: str = ""


@dataclass
class Masker:
    """Blank what is not code, carrying the state a line leaves for the next."""

    heredoc: str | None = None
    commented: bool = False

    def line(self, text: str) -> tuple[str, str]:
        """Mask one line for brace matching and for reference reading.

        Args:
            text: The line to mask, without its newline.

        Returns:
            The line with its strings, comments and heredoc body blanked, and
            the same line with only its comments blanked, both the length of
            the input so that offsets into either reach the same characters.
        """
        if self.heredoc is not None:
            return self._within_heredoc(text)
        if self.commented:
            return self._within_comment(text)
        return self._within_code(text)

    def _within_heredoc(self, text: str) -> tuple[str, str]:
        """Mask a line of a heredoc body, or the terminator that ends one."""
        if text.strip() == self.heredoc:
            self.heredoc = None
            return (text, text)
        return (blank(text), text)

    def _within_comment(self, text: str) -> tuple[str, str]:
        """Mask a line inside a block comment opened on an earlier line."""
        closed = text.find("*/")
        if closed < 0:
            return (blank(text), blank(text))
        self.commented = False
        head = blank(text[: closed + 2])
        structure, uncommented = self._within_code(text[closed + 2 :])
        return (head + structure, head + uncommented)

    def _within_code(self, text: str) -> tuple[str, str]:
        """Mask a line that starts outside every string, comment and heredoc."""
        stringless = STRING.sub(lambda match: blank_string(match.group(0)), text)
        commented = [match.span() for match in BLOCK_COMMENT.finditer(stringless)]
        stringless = blank_spans(stringless, commented)
        cut = self._cut(stringless)
        started = HEREDOC.search(stringless[:cut])
        if started is not None:
            self.heredoc = started.group(1)
        commented.append((cut, len(text)))
        return (blank_spans(stringless, [(cut, len(text))]), blank_spans(text, commented))

    def _cut(self, stringless: str) -> int:
        """Find where the comment that runs to the end of the line starts."""
        opened = OPEN_COMMENT.search(stringless)
        if opened is not None:
            self.commented = True
            return opened.start()
        comment = LINE_COMMENT.search(stringless)
        return comment.start() if comment is not None else len(stringless)


def blank(text: str) -> str:
    """Replace every character of a string with a space."""
    return " " * len(text)


def blank_string(literal: str) -> str:
    """Blank the body of a quoted string, keeping the quotes that delimit it."""
    return literal[0] + blank(literal[1:-1]) + literal[-1]


def blank_spans(text: str, spans: Iterable[tuple[int, int]]) -> str:
    """Replace the given ranges of a string with spaces.

    Args:
        text: The string to blank.
        spans: Half-open ranges to blank, which may overlap.

    Returns:
        The string with those ranges spaced out, the same length as the input.
    """
    characters = list(text)
    for start, end in spans:
        characters[start:end] = blank(text[start:end])
    return "".join(characters)


def masks(content: str) -> tuple[str, str]:
    """Mask a whole file for brace matching and for reference reading.

    Args:
        content: The file content.

    Returns:
        The structure mask and the uncommented mask, both the length of the
        input.
    """
    masker = Masker()
    masked = [masker.line(line) for line in content.split("\n")]
    return ("\n".join(pair[0] for pair in masked), "\n".join(pair[1] for pair in masked))


def close_brace(structure: str, opening: int) -> int:
    """Find where the block a brace opens ends.

    Args:
        structure: The structure mask of the file.
        opening: The offset of the opening brace.

    Returns:
        The offset just past the matching closing brace, or the end of the
        file where the braces never balance.
    """
    depth = 0
    for index in range(opening, len(structure)):
        if structure[index] == "{":
            depth += 1
        elif structure[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(structure)


def blocks_of(path: str, text: str, structure: str) -> tuple[Block, ...]:
    """Find every top-level block of one file.

    A header is read only where the structure mask agrees that its brace is
    code, so a line of a heredoc body that reads like one is left alone.

    Args:
        path: The file path, used for reporting.
        text: The file content.
        structure: The structure mask of the file.

    Returns:
        The blocks, in the order they are written.
    """
    found: list[Block] = []
    for match in BLOCK_HEADER.finditer(text):
        opening = match.end() - 1
        if structure[opening] != "{":
            continue
        found.append(
            Block(
                path=path,
                line_number=text.count("\n", 0, match.start()) + 1,
                kind=match.group(1),
                labels=tuple(LABEL.findall(match.group(2))),
                opening=opening,
                end=close_brace(structure, opening),
            )
        )
    return tuple(found)


def read_source(path: str, text: str) -> Source:
    """Read one .tf file into the form every test below works from.

    Args:
        path: The file path, used for reporting.
        text: The file content.

    Returns:
        The file, its two masks and its top-level blocks.
    """
    structure, uncommented = masks(text)
    return Source(
        path=path,
        text=text,
        structure=structure,
        uncommented=uncommented,
        blocks=blocks_of(path, text, structure),
    )


def address_of(block: Block) -> str | None:
    """Name the address a block is reached by.

    Args:
        block: The block to read.

    Returns:
        The address, or None for a block nothing addresses that way.
    """
    if block.kind == RESOURCE and len(block.labels) == 2:
        return f"{block.labels[0]}.{block.labels[1]}"
    if block.kind == DATA and len(block.labels) == 2:
        return f"data.{block.labels[0]}.{block.labels[1]}"
    if block.kind == MODULE and len(block.labels) == 1:
        return f"module.{block.labels[0]}"
    return None


def reference(address: str) -> re.Pattern[str]:
    """Build the pattern that matches an address and nothing longer."""
    return re.compile(rf"(?<![A-Za-z0-9_.]){re.escape(address)}(?![A-Za-z0-9_])")


def resources(sources: Sequence[Source]) -> Iterator[Block]:
    """Walk every resource block of a directory, in file and line order."""
    for source in sources:
        for block in source.blocks:
            if block.kind == RESOURCE and len(block.labels) == 2:
                yield block


def addresses(sources: Sequence[Source]) -> set[str]:
    """Collect every address the directory's resources, data and modules carry."""
    found = {address_of(block) for source in sources for block in source.blocks}
    return {address for address in found if address is not None}


def output_names(sources: Sequence[Source]) -> set[str]:
    """Collect the name of every output the directory publishes."""
    return {
        block.labels[0]
        for source in sources
        for block in source.blocks
        if block.kind == OUTPUT and block.labels
    }


def output_is_read(name: str, corpus: Corpus) -> bool:
    """Check whether anything reads one output of the directory.

    Three things read one: a remote state reference in another subsystem's
    OpenTofu, a terraform_output call in Python, and a terraform output -raw
    step in a workflow. An output nothing reads publishes nothing.

    Args:
        name: The output name.
        corpus: The text a use may be credited from.

    Returns:
        True where one of the three reads it.
    """
    escaped = re.escape(name)
    return bool(
        re.search(rf"\.outputs\.{escaped}(?![A-Za-z0-9_])", corpus.terraform)
        or re.search(rf"terraform_output\([^)]*[\"']{escaped}[\"']", corpus.python)
        or re.search(rf"output[ \t]+-raw[ \t]+{escaped}(?![A-Za-z0-9_])", corpus.workflows)
    )


def read_outputs(sources: Sequence[Source], corpus: Corpus) -> set[str]:
    """Collect the outputs of the directory that something reads."""
    return {name for name in output_names(sources) if output_is_read(name, corpus)}


def body_of(source: Source, block: Block) -> str:
    """Read the text a block's braces enclose, with its comments blanked."""
    return source.uncommented[block.opening + 1 : block.end - 1]


def spans_of(source: Source, block: Block) -> str:
    """Read the structure mask a block's braces enclose."""
    return source.structure[block.opening + 1 : block.end - 1]


def assignments_of(source: Source, block: Block) -> list[tuple[str, str]]:
    """Read every string a top-level attribute of a block is assigned.

    An attribute written inside a nested block or a list belongs to that
    rather than to the resource, so the depth the structure mask reports is
    what decides which lines are read.

    Args:
        source: The file the block was read from.
        block: The block to read.

    Returns:
        The attribute name and the string it is assigned, in written order.
    """
    found: list[tuple[str, str]] = []
    depth = 0
    for line, guide in zip(body_of(source, block).split("\n"), spans_of(source, block).split("\n")):
        match = ASSIGNED.match(line)
        if depth == 0 and match is not None:
            found.append((match.group(1), match.group(2)))
        depth += sum(guide.count(character) for character in OPENERS)
        depth -= sum(guide.count(character) for character in CLOSERS)
    return found


@dataclass(frozen=True)
class Subsystem:
    """One directory of OpenTofu, and everything the tests below ask of it."""

    sources: tuple[Source, ...]
    corpus: Corpus
    known: set[str] = field(default_factory=set)
    published: set[str] = field(default_factory=set)


def subsystem(sources: Sequence[Source], corpus: Corpus) -> Subsystem:
    """Read a directory of OpenTofu into the form the four tests work from."""
    return Subsystem(
        sources=tuple(sources),
        corpus=corpus,
        known=addresses(sources),
        published=read_outputs(sources, corpus),
    )


def within(block: Block, source: Source, position: int) -> bool:
    """Check whether an offset in a file falls inside one block of it."""
    return source.path == block.path and block.opening <= position < block.end


def enclosing(source: Source, position: int) -> Block | None:
    """Find the top-level block an offset in a file falls inside, if any."""
    for block in source.blocks:
        if block.opening <= position < block.end:
            return block
    return None


def counts_as_use(source: Source, position: int, published: set[str]) -> bool:
    """Check whether an interpolation at an offset is a use of what it names.

    An interpolation inside an output block is a use only where something
    reads that output. Everywhere else it is one on sight.

    Args:
        source: The file the interpolation was found in.
        position: The offset it was found at.
        published: The outputs of the directory that something reads.

    Returns:
        True where the interpolation credits what it names.
    """
    block = enclosing(source, position)
    if block is None or block.kind != OUTPUT:
        return True
    return bool(block.labels) and block.labels[0] in published


def address_is_used(block: Block, address: str, scope: Subsystem) -> bool:
    """Check whether anything else in the directory interpolates an address."""
    pattern = reference(address)
    for source in scope.sources:
        for match in pattern.finditer(source.uncommented):
            if within(block, source, match.start()):
                continue
            if counts_as_use(source, match.start(), scope.published):
                return True
    return False


def body_attaches(source: Source, block: Block, address: str, scope: Subsystem) -> bool:
    """Check whether a block's own body interpolates something of the directory.

    A resource attached at one end is attached, so a body naming another
    resource, a data source or a module of the same directory is enough.

    Args:
        source: The file the block was read from.
        block: The block to read.
        address: The block's own address, which naming does not count.
        scope: The directory the block belongs to.

    Returns:
        True where the body names another address of the directory.
    """
    body = body_of(source, block)
    return any(reference(other).search(body) for other in scope.known if other != address)


def value_is_repeated(
    block: Block, assignments: Sequence[tuple[str, str]], scope: Subsystem
) -> bool:
    """Check whether a string the block assigns is spelled again elsewhere.

    This is attachment by value rather than by address: an SES identity whose
    address is spelled again in a policy and in an environment variable is
    what makes those two work, and nothing interpolates it.

    Args:
        block: The block to read.
        assignments: The strings its top-level attributes are assigned.
        scope: The directory the block belongs to.

    Returns:
        True where one of the strings appears outside the block.
    """
    for literal in {value for _, value in assignments if value}:
        for source in scope.sources:
            start = source.uncommented.find(literal)
            while start >= 0:
                if not within(block, source, start):
                    return True
                start = source.uncommented.find(literal, start + 1)
    return False


def identity_fragments(assignments: Sequence[tuple[str, str]]) -> list[str]:
    """Split the block's identity attributes into the literal parts of them.

    Args:
        assignments: The strings the top-level attributes are assigned.

    Returns:
        Every non-empty part left once the interpolations are taken out.
    """
    return [
        fragment
        for attribute, literal in assignments
        if attribute in IDENTITY_ATTRIBUTES
        for fragment in INTERPOLATION.split(literal)
        if fragment
    ]


def identity_is_reached(assignments: Sequence[tuple[str, str]], corpus: Corpus) -> bool:
    """Check whether a program outside OpenTofu spells the deployed identifier.

    A resource reached by name from Python, from a workflow or from a script
    is reached, and the parameters the bootstrap publishes are the case this
    credits. A block carrying none of the known identity spellings has no
    fragment to look for and is not credited.

    Args:
        assignments: The strings the top-level attributes are assigned.
        corpus: The text a use may be credited from.

    Returns:
        True where a fragment of the identifier appears in a program file.
    """
    return any(fragment in corpus.programs for fragment in identity_fragments(assignments))


def is_detached(source: Source, block: Block, scope: Subsystem) -> bool:
    """Check whether a resource is reached by nothing at all.

    Args:
        source: The file the resource was read from.
        block: The resource block.
        scope: The directory it belongs to.

    Returns:
        True where all four tests hold, which is what separates a detached
        resource from a legitimately terminal one.
    """
    address = f"{block.labels[0]}.{block.labels[1]}"
    assignments = assignments_of(source, block)
    return not (
        address_is_used(block, address, scope)
        or body_attaches(source, block, address, scope)
        or value_is_repeated(block, assignments, scope)
        or identity_is_reached(assignments, scope.corpus)
    )


def detached_resources(sources: Sequence[Source], corpus: Corpus) -> list[Finding]:
    """Find every resource of a directory that nothing reaches.

    Args:
        sources: The .tf files of one subsystem directory.
        corpus: The text a use may be credited from.

    Returns:
        A finding for each detached resource, in file and line order.
    """
    scope = subsystem(sources, corpus)
    by_path = {source.path: source for source in sources}
    return [
        Finding(block.path, block.line_number, f"{block.labels[0]}.{block.labels[1]}")
        for block in resources(sources)
        if is_detached(by_path[block.path], block, scope)
    ]
