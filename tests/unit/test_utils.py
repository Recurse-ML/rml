from textwrap import dedent

import pytest

from rml.datatypes import APICommentResponse, SourceLocation
from rml.utils import enrich_bc_ref_locations_with_source


@pytest.fixture(scope="function")
def filepath_1(tmp_path):
    file_path = tmp_path / "test_1.py"
    file_path.write_text("def test_1(): pass")
    return file_path


@pytest.fixture(scope="function")
def filepath_2(tmp_path):
    file_path = tmp_path / "test_2.py"
    file_path.write_text("def test_2(): pass")
    return file_path


@pytest.fixture(scope="function")
def filepath_3(tmp_path):
    file_path = tmp_path / "test_3.py"
    file_path.write_text("def test_3(): pass")
    return file_path


def test_enrich_bc_ref_locations_with_source_adds_source_for_ref_locations(
    filepath_1, filepath_2
):
    comment_body = dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {filepath_2.name}:1
    """)
    comment = APICommentResponse(
        body=comment_body,
        diff_str="",
        relative_path=str(filepath_1),
        line_no=1,
        reference_locations=[
            SourceLocation(relative_path=str(filepath_2), line_no=1),
        ],
    )

    enriched_body = enrich_bc_ref_locations_with_source(comment)

    expected = (
        "\n"
        + dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {str(filepath_2)}:1
    ```python
    def test_2(): pass
    ```
    """).lstrip()
    )

    assert enriched_body == expected


def test_enrich_bc_ref_locations_with_source_returns_none_if_error_occurs_while_reading_all_ref_location_lines(
    filepath_1, filepath_2
):
    comment_body = dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {filepath_2.name}:1
    """)
    comment = APICommentResponse(
        body=comment_body,
        diff_str="",
        relative_path=str(filepath_1),
        line_no=1,
        reference_locations=[
            SourceLocation(relative_path=str(filepath_2), line_no=1),
        ],
    )

    filepath_2.unlink()  # Will cause a FileNotFoundError

    enriched_body = enrich_bc_ref_locations_with_source(comment)

    assert enriched_body is None


def test_enrich_bc_ref_locations_with_source_keeps_only_reference_locations_that_exist(
    filepath_1, filepath_2, filepath_3
):
    comment_body = dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {str(filepath_2)}:1
    {str(filepath_3)}:1
    """)
    comment = APICommentResponse(
        body=comment_body,
        diff_str="",
        relative_path=str(filepath_1),
        line_no=1,
        reference_locations=[
            SourceLocation(relative_path=str(filepath_2), line_no=1),
            SourceLocation(relative_path=str(filepath_3), line_no=1),
        ],
    )

    filepath_3.unlink()  # Will cause a FileNotFoundError

    enriched_body = enrich_bc_ref_locations_with_source(comment)

    expected = (
        "\n"
        + dedent(f"""
    This change breaks 1 usages of `test_1` across 1 files

    #Symbol: `test_1`
    
    ## Affected locations

    {str(filepath_2)}:1
    ```python
    def test_2(): pass
    ```
    """).lstrip()
    )

    assert enriched_body == expected
