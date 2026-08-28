"""Unit test configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from assert_opentofu_resource_is_used.scanner import (
    Corpus,
    Source,
    detached_resources,
    read_source,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def read() -> Callable[[str], Source]:
    """Read one .tf text as a file called main.tf.

    Returns:
        A function taking the text and returning the source read from it.
    """

    def reader(text: str) -> Source:
        return read_source("main.tf", text)

    return reader


@pytest.fixture
def addresses_refused() -> Callable[..., list[str]]:
    """Name the resources the four tests refuse in one directory.

    Returns:
        A function taking a mapping of file name to content and an optional
        corpus, and returning the address of every resource refused.
    """

    def runner(files: dict[str, str], corpus: Corpus | None = None) -> list[str]:
        sources = [read_source(name, text) for name, text in files.items()]
        findings = detached_resources(sources, corpus if corpus is not None else Corpus())
        return [finding.address for finding in findings]

    return runner
