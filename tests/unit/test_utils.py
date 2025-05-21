from pathlib import Path
from textwrap import dedent
from rml.datatypes import APICommentResponse, SourceLocation
from rml.utils import enrich_bc_markdown_with_source
from unittest.mock import patch
import pytest


@pytest.fixture(scope="function")
def file_1(tmpdir):
    file = tmpdir.join("test_1.py")
    file.write("def test_1(): pass")
    return file


@pytest.fixture(scope="function")
def file_2(tmpdir):
    file = tmpdir.join("test_2.py")
    file.write("def test_2(): pass")
    return file


def test_enrich_bc_markdown_with_source_adds_source_for_bc_and_ref_locations(
    file_1, file_2
):
    comment_body = dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {file_2.strpath}:1
    """)
    comment = APICommentResponse(
        body=comment_body,
        diff_str="",
        relative_path=file_1.strpath,
        line_no=1,
        reference_locations=[
            SourceLocation(relative_path=file_2.strpath, line_no=1),
        ],
    )

    enriched_body = enrich_bc_markdown_with_source(comment)

    assert (
        enriched_body
        == dedent(f"""
    ```python
    def test_1(): pass
    ```

    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {file_2.strpath}:1
    ```python
    def test_2(): pass
    ```
    """).lstrip()
    )


def test_enrich_bc_markdown_with_source_returns_none_if_error_occurs_while_reading_bc_line(
    file_1, file_2
):
    comment_body = dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {file_2.strpath}:1
    """)
    comment = APICommentResponse(
        body=comment_body,
        diff_str="",
        relative_path=file_1.strpath,
        line_no=1,
        reference_locations=[
            SourceLocation(relative_path=file_2.strpath, line_no=1),
        ],
    )

    with patch("rml.utils.Path.read_text", side_effect=FileNotFoundError()):
        enriched_body = enrich_bc_markdown_with_source(comment)

    assert enriched_body is None
