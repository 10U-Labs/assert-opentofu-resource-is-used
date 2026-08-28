"""Unit tests for the scanner."""

from __future__ import annotations

from test.samples import (
    ADDRESSED,
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

from assert_opentofu_resource_is_used.scanner import (
    Block,
    Corpus,
    Finding,
    Masker,
    addresses,
    address_of,
    assignments_of,
    blank,
    blank_spans,
    blank_string,
    close_brace,
    counts_as_use,
    enclosing,
    identity_fragments,
    identity_is_reached,
    masks,
    output_is_read,
    output_names,
    read_outputs,
    read_source,
    resources,
    subsystem,
    within,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from assert_opentofu_resource_is_used.scanner import Source

NO_LABEL_OUTPUT = 'output {\n  value = aws_dynamodb_table.audit.name\n}\n'


@pytest.mark.unit
class TestMasking:
    """Tests for blanking what is not code."""

    def test_blank_keeps_length(self) -> None:
        """Blanking a run of characters gives back as many spaces."""
        assert blank("abcd") == "    "

    def test_blank_string_keeps_quotes(self) -> None:
        """Blanking a string literal leaves the quotes that delimit it."""
        assert blank_string('"ab"') == '"  "'

    def test_blank_string_of_empty_literal(self) -> None:
        """An empty literal is already blank between its quotes."""
        assert blank_string('""') == '""'

    def test_blank_spans_leaves_the_rest(self) -> None:
        """Only the ranges named are spaced out."""
        assert blank_spans("abcdef", [(1, 3)]) == "a  def"

    def test_masks_keep_the_length(self) -> None:
        """The structure mask is as long as the file it was read from."""
        assert len(masks(HEREDOC)[0]) == len(HEREDOC)

    def test_masks_keep_the_length_uncommented(self) -> None:
        """The uncommented mask is as long as the file it was read from."""
        assert len(masks(HEREDOC)[1]) == len(HEREDOC)

    def test_structure_blanks_a_string_body(self) -> None:
        """A brace inside a string is not code."""
        assert "{" not in masks('a = "{"\n')[0]

    def test_uncommented_keeps_a_string_body(self) -> None:
        """A reference inside a string is still a reference."""
        assert "aws_x.y" in masks('a = "${aws_x.y}"\n')[1]

    def test_heredoc_body_is_not_structure(self) -> None:
        """An unbalanced brace in a heredoc body cannot close a block."""
        assert masks(HEREDOC)[0].count("{") == 1

    def test_heredoc_body_is_read_for_references(self) -> None:
        """A heredoc naming a resource names it."""
        assert "aws_dynamodb_table.audit" in masks(HEREDOC)[1]

    def test_hash_comment_is_blanked(self) -> None:
        """A reference behind a hash is not one."""
        assert "aws_dynamodb_table.audit" not in masks(HASH_COMMENT)[1]

    def test_block_comment_is_blanked(self) -> None:
        """A reference inside a one-line block comment is not one."""
        assert "aws_dynamodb_table.audit" not in masks(COMMENTED)[1]

    def test_spanning_comment_is_blanked(self) -> None:
        """A reference inside a block comment spanning lines is not one."""
        assert "aws_dynamodb_table.audit" not in masks(SPANNING_COMMENT)[1]

    def test_spanning_comment_releases_the_line_it_closes_on(self) -> None:
        """What follows the close of a block comment is code again."""
        assert "name" in masks(SPANNING_COMMENT)[1]

    def test_an_unclosed_comment_swallows_the_file(self) -> None:
        """A block comment nothing closes runs to the end."""
        assert masks("/* one\ntwo\n")[1].strip() == ""

    def test_a_masker_starts_outside_everything(self) -> None:
        """A fresh masker is in no heredoc."""
        assert Masker().heredoc is None


@pytest.mark.unit
class TestBlocks:
    """Tests for finding the top-level blocks of a file."""

    def test_a_resource_is_found(self, read: Callable[[str], Source]) -> None:
        """A resource block is one block."""
        assert len(read(DETACHED).blocks) == 1

    def test_a_header_in_a_heredoc_is_not_a_block(self, read: Callable[[str], Source]) -> None:
        """A line of a heredoc body that reads like a header is not one."""
        assert len(read(HEREDOC).blocks) == 1

    def test_a_block_carries_its_line(self, read: Callable[[str], Source]) -> None:
        """A block is reported at the line its header is written on."""
        assert read(EXPORTED + DETACHED).blocks[1].line_number == 4

    def test_unbalanced_braces_end_at_the_file(self, read: Callable[[str], Source]) -> None:
        """A block nothing closes ends where the file does."""
        assert read(UNBALANCED).blocks[0].end == len(UNBALANCED)

    def test_close_brace_finds_the_match(self) -> None:
        """The matching brace is the one that brings the depth back to zero."""
        assert close_brace("{ { } }", 0) == 7

    def test_a_resource_address_is_type_and_name(self, read: Callable[[str], Source]) -> None:
        """A resource is addressed by its type and its name."""
        assert address_of(read(DETACHED).blocks[0]) == "aws_dynamodb_table.audit"

    def test_a_data_address_carries_its_prefix(self, read: Callable[[str], Source]) -> None:
        """A data source is addressed through data."""
        assert address_of(read(REMOTE_STATE_READER).blocks[0]) == (
            "data.terraform_remote_state.routing"
        )

    def test_a_module_address_is_its_name(self, read: Callable[[str], Source]) -> None:
        """A module is addressed by its one label."""
        assert address_of(read('module "docs" {\n  source = "./docs"\n}\n').blocks[0]) == (
            "module.docs"
        )

    def test_a_locals_block_has_no_address(self, read: Callable[[str], Source]) -> None:
        """Nothing addresses a locals block that way."""
        assert address_of(read("locals {\n  a = 1\n}\n").blocks[0]) is None

    def test_addresses_collects_every_kind(self, read: Callable[[str], Source]) -> None:
        """The directory knows the addresses its blocks carry."""
        assert addresses([read(REMOTE_STATE_READER)]) == {
            "data.terraform_remote_state.routing",
            "aws_iam_role.other",
        }

    def test_resources_leaves_out_the_rest(self, read: Callable[[str], Source]) -> None:
        """Only resource blocks are walked as resources."""
        assert [block.labels[1] for block in resources([read(REMOTE_STATE_READER)])] == ["other"]


@pytest.mark.unit
class TestAssignments:
    """Tests for reading the strings a block's top-level attributes carry."""

    def test_a_top_level_string_is_read(self, read: Callable[[str], Source]) -> None:
        """An attribute written at the top of the block is read."""
        source = read(DETACHED)
        assert ("billing_mode", "PAY_PER_REQUEST") in assignments_of(source, source.blocks[0])

    def test_a_nested_string_is_not_read(self, read: Callable[[str], Source]) -> None:
        """An attribute inside a list belongs to the list."""
        source = read(LISTED)
        assert [name for name, _ in assignments_of(source, source.blocks[0])] == ["name"]

    def test_a_nested_block_is_not_read(self, read: Callable[[str], Source]) -> None:
        """An attribute inside a nested block belongs to that block."""
        source = read(ADDRESSED)
        assert [name for name, _ in assignments_of(source, source.blocks[0])] == ["function_name"]


@pytest.mark.unit
class TestOutputs:
    """Tests for deciding whether an output is read."""

    def test_output_names_are_collected(self, read: Callable[[str], Source]) -> None:
        """An output is known by its one label."""
        assert output_names([read(EXPORTED)]) == {"audit_table_name"}

    def test_remote_state_reads_an_output(self) -> None:
        """Another subsystem's OpenTofu reads one."""
        assert output_is_read("audit_table_name", Corpus(terraform=REMOTE_STATE_READER))

    def test_python_reads_an_output(self) -> None:
        """A terraform_output call reads one."""
        assert output_is_read("audit_table_name", Corpus(python=TERRAFORM_OUTPUT_READER))

    def test_a_workflow_reads_an_output(self) -> None:
        """A terraform output -raw step reads one."""
        assert output_is_read("audit_table_name", Corpus(workflows=WORKFLOW_READER))

    def test_a_longer_name_is_not_the_same_output(self) -> None:
        """An output whose name is a prefix of another is not read by it."""
        assert not output_is_read("audit_table", Corpus(terraform=REMOTE_STATE_READER))

    def test_read_outputs_keeps_only_the_read(self, read: Callable[[str], Source]) -> None:
        """An output nothing reads is not published."""
        assert read_outputs([read(EXPORTED)], Corpus()) == set()


@pytest.mark.unit
class TestPlacement:
    """Tests for deciding where in a file an interpolation sits."""

    def test_within_its_own_block(self, read: Callable[[str], Source]) -> None:
        """An offset inside a block is within it."""
        source = read(DETACHED)
        assert within(source.blocks[0], source, source.blocks[0].opening + 1)

    def test_not_within_another_file(self, read: Callable[[str], Source]) -> None:
        """A block of one file holds no offset of another."""
        block = read(DETACHED).blocks[0]
        assert not within(block, read_source("other.tf", DETACHED), block.opening + 1)

    def test_not_within_past_the_end(self, read: Callable[[str], Source]) -> None:
        """An offset past the closing brace is outside the block."""
        source = read(DETACHED)
        assert not within(source.blocks[0], source, source.blocks[0].end)

    def test_enclosing_finds_the_block(self, read: Callable[[str], Source]) -> None:
        """An offset inside a block is enclosed by it."""
        source = read(DETACHED)
        found = enclosing(source, source.blocks[0].opening + 1)
        assert found is not None and found.labels == ("aws_dynamodb_table", "audit")

    def test_enclosing_finds_nothing_outside(self, read: Callable[[str], Source]) -> None:
        """An offset in no block is enclosed by none."""
        assert enclosing(read(STRAY), 0) is None

    def test_an_interpolation_outside_a_block_is_a_use(self, read: Callable[[str], Source]) -> None:
        """Text belonging to no block is credited on sight."""
        assert counts_as_use(read(STRAY), 0, set())

    def test_an_unread_output_is_not_a_use(self, read: Callable[[str], Source]) -> None:
        """Exporting a resource nothing asks for is not using it."""
        source = read(EXPORTED)
        assert not counts_as_use(source, source.blocks[0].opening + 1, set())

    def test_a_read_output_is_a_use(self, read: Callable[[str], Source]) -> None:
        """Exporting a resource something reads is using it."""
        source = read(EXPORTED)
        assert counts_as_use(source, source.blocks[0].opening + 1, {"audit_table_name"})

    def test_an_output_without_a_name_is_not_a_use(self, read: Callable[[str], Source]) -> None:
        """An output nothing can address publishes nothing."""
        source = read(NO_LABEL_OUTPUT)
        assert not counts_as_use(source, source.blocks[0].opening + 1, {"audit_table_name"})


@pytest.mark.unit
class TestIdentity:
    """Tests for reaching a resource by the identifier it deploys under."""

    def test_fragments_drop_the_interpolations(self, read: Callable[[str], Source]) -> None:
        """What is left of a name is the part written out."""
        source = read(DETACHED)
        assert identity_fragments(assignments_of(source, source.blocks[0])) == ["AuditTrail"]

    def test_a_program_naming_the_identifier_reaches_it(
        self, read: Callable[[str], Source]
    ) -> None:
        """A parameter read by name from Python is reached."""
        source = read(PARAMETER)
        assignments = assignments_of(source, source.blocks[0])
        assert identity_is_reached(assignments, Corpus(programs=PARAMETER_READER))

    def test_a_program_naming_nothing_reaches_nothing(self, read: Callable[[str], Source]) -> None:
        """A corpus that never spells the identifier credits nothing."""
        source = read(DETACHED)
        assert not identity_is_reached(assignments_of(source, source.blocks[0]), Corpus())


@pytest.mark.unit
class TestRefusal:
    """Tests for the four tests together."""

    def test_a_detached_table_is_refused(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A resource nothing reaches is refused."""
        assert addresses_refused({"db.tf": DETACHED}) == ["aws_dynamodb_table.audit"]

    def test_an_unread_export_does_not_save_it(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A resource interpolated only by an output nothing reads is refused."""
        assert addresses_refused({"db.tf": DETACHED, "outputs.tf": EXPORTED}) == [
            "aws_dynamodb_table.audit"
        ]

    def test_a_read_export_saves_it(self, addresses_refused: Callable[..., list[str]]) -> None:
        """A resource interpolated by an output another subsystem reads is kept."""
        assert not addresses_refused(
            {"db.tf": DETACHED, "outputs.tf": EXPORTED},
            Corpus(terraform=REMOTE_STATE_READER),
        )

    def test_an_interpolation_saves_it(self, addresses_refused: Callable[..., list[str]]) -> None:
        """A resource another resource names is kept."""
        assert not addresses_refused({"db.tf": DETACHED, "lambda.tf": ADDRESSED})

    def test_a_body_that_names_something_saves_it(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A resource attached at one end is attached."""
        assert "aws_lambda_permission.invoke" not in addresses_refused(
            {"db.tf": DETACHED, "permission.tf": ATTACHING}
        )

    def test_a_repeated_string_saves_it(self, addresses_refused: Callable[..., list[str]]) -> None:
        """An identity spelled again in a policy is reached by value."""
        assert not addresses_refused({"contact.tf": VALUED})

    def test_a_program_naming_it_saves_it(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A parameter read by name from outside OpenTofu is kept."""
        assert not addresses_refused(
            {"ssm.tf": PARAMETER}, Corpus(programs=PARAMETER_READER)
        )

    def test_a_blank_string_repeats_nothing(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """An attribute assigned nothing cannot attach the block by value."""
        assert addresses_refused({"role.tf": BLANK_NAME}) == ["aws_iam_role.blank"]

    def test_a_block_naming_itself_saves_nothing(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A resource is not credited with a use written inside itself."""
        assert addresses_refused({"role.tf": SELF_NAMING}) == ["aws_iam_role.circular"]

    def test_a_commented_reference_saves_nothing(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A resource named only in a comment is reached by nothing."""
        assert "aws_dynamodb_table.audit" in addresses_refused(
            {"db.tf": DETACHED, "role.tf": HASH_COMMENT}
        )

    def test_a_heredoc_reference_saves_it(
        self, addresses_refused: Callable[..., list[str]]
    ) -> None:
        """A resource named in a heredoc body is named."""
        assert "aws_dynamodb_table.audit" not in addresses_refused(
            {"db.tf": DETACHED, "function.tf": HEREDOC}
        )

    def test_a_subsystem_knows_what_it_publishes(self, read: Callable[[str], Source]) -> None:
        """The outputs something reads are carried with the directory."""
        scope = subsystem([read(EXPORTED)], Corpus(workflows=WORKFLOW_READER))
        assert scope.published == {"audit_table_name"}


@pytest.mark.unit
class TestFinding:
    """Tests for how a finding reads."""

    def test_a_finding_reads_as_path_line_address(self) -> None:
        """A finding is printed as path, line and address."""
        assert str(Finding("db.tf", 1, "aws_dynamodb_table.audit")) == (
            "db.tf:1:aws_dynamodb_table.audit"
        )

    def test_a_block_carries_the_path_it_came_from(self, read: Callable[[str], Source]) -> None:
        """A block knows which file declared it."""
        assert isinstance(read(DETACHED).blocks[0], Block)
