from enum import Enum
from typing import List, NamedTuple, Optional

from pydantic import BaseModel, field_validator


class SourceLocation(BaseModel):
    relative_path: str
    line_no: int


class APICommentResponse(BaseModel):
    body: str
    diff_str: str
    relative_path: str
    line_no: int
    documentation_url: Optional[str] = None
    reference_locations: Optional[List[SourceLocation]] = None

    @field_validator("reference_locations", mode="before")
    @classmethod
    def convert_reference_locations(cls, value):
        if isinstance(value, list):
            return [
                SourceLocation(**loc) if isinstance(loc, dict) else loc for loc in value
            ]
        return value

    class Config:
        from_attributes = True


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


class AuthStatus(Enum):
    SUCCESS = "success"
    PENDING = "pending"
    EXPIRED = "expired"
    DENIED = "denied"
    ERROR = "error"
    CANCELLED = "cancelled"


class AuthResult(BaseModel):
    status: AuthStatus
    access_token: Optional[str] = None
    error_message: Optional[str] = None
