"""Unit test configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from assert_opentofu_resource_is_used.scanner import (
    Corpus,
    Finding,
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
def refused() -> Callable[..., list[Finding]]:
    """Run the four tests over one directory given as files and a corpus.

    Returns:
        A function taking a mapping of file name to content and an optional
        corpus, and returning the findings.
    """

    def runner(files: dict[str, str], corpus: Corpus | None = None) -> list[Finding]:
        sources = [read_source(name, text) for name, text in files.items()]
        return detached_resources(sources, corpus if corpus is not None else Corpus())

    return runner


@pytest.fixture
def addresses_refused(refused: Callable[..., list[Finding]]) -> Callable[..., list[str]]:
    """Name the resources one directory's four tests refuse.

    Returns:
        A function taking the same arguments as the refused fixture and
        returning the addresses rather than the findings.
    """

    def runner(files: dict[str, str], corpus: Corpus | None = None) -> list[str]:
        return [finding.address for finding in refused(files, corpus)]

    return runner
