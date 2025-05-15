from typing import Optional, NamedTuple
from enum import Enum

from pydantic import BaseModel

class Operator(Enum):
    ADD = "+"
    REMOVE = "-"
    REPLACE = "R"
    NO_CHANGE = " "

class DiffLine(NamedTuple):
    operator: Operator
    content: str
    old_line_idx: Optional[int] = None
    new_line_idx: Optional[int] = None
    replacement: Optional[str] = None

    def __str__(self):
        old_line_idx = f"{self.old_line_idx}" if self.old_line_idx is not None else "x"
        new_line_idx = f"{self.new_line_idx}" if self.new_line_idx is not None else "x"
        return f"{old_line_idx}|{new_line_idx} {self.operator.value} {self.content}"



class Diff(NamedTuple):
    old_start_line_idx: int
    new_start_line_idx: int
    old_len: int
    new_len: int
    changes: list[DiffLine]


class CommentClassification(Enum):
    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"

class Comment(BaseModel):
    relative_path: str
    line_no: int
    body: str
    head_source: str
    diff_line: Optional[DiffLine] = None
    classification: Optional[CommentClassification] = None
    documentation_url: Optional[str] = None
    created_by: Optional[str] = None
