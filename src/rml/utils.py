import re
import time
from rml.datatypes import DiffLine, Operator, Diff

DIFF_HEADER_PTRN = re.compile(
    r"@@\s-(?P<old_start>\d+)(?:,(?P<old_len>\d+))?\s+\+(?P<new_start>\d+)(?:,(?P<new_len>\d+))?\s@@"
)
DIFF_LINE_PTRN = re.compile(r"(?P<old_no>\d+|x)\|(?P<new_no>\d+|x)")


def parse_diff_str_single_hunk(diff_str: str) -> Diff:
    """Parse a diff string consisting of a single hunk"""
    diff_str_lines = iter(diff_str.splitlines(keepends=True))

    for line in diff_str_lines:
        if header_match := DIFF_HEADER_PTRN.match(line):
            old_start_line_no = int(header_match.group("old_start"))
            old_start_line_idx = old_start_line_no - 1  # Convert to 0-based indexing
            new_start_line_no = int(header_match.group("new_start"))
            new_start_line_idx = new_start_line_no - 1
            # In unified diff format if length is not specified, it is assumed to be 1
            old_len = int(header_match.group("old_len") or 1)
            new_len = int(header_match.group("new_len") or 1)
            break
    else:
        raise ValueError(f"Invalid diff format: {diff_str}")

    diff_lines = []
    curr_old_line_idx = old_start_line_idx
    curr_new_line_idx = new_start_line_idx
    for diff_str_line in diff_str_lines:
        if (diff_str_line.strip() == "") and (diff_str_line[:1] != " "):
            continue

        if diff_str_line.startswith(r"\ No newline at end of file"):
            continue

        cur_op, content = diff_str_line[0], diff_str_line[1:]
        assert cur_op in ("+", "-", " "), f"Couldn't parse diff line: '{diff_str_line}'"

        if cur_op == "+":
            new_line_idx = curr_new_line_idx
            curr_new_line_idx += 1
            old_line_idx = None
        elif cur_op == "-":
            old_line_idx = curr_old_line_idx
            curr_old_line_idx += 1
            new_line_idx = None
        elif cur_op == " ":
            old_line_idx = curr_old_line_idx
            new_line_idx = curr_new_line_idx
            curr_old_line_idx += 1
            curr_new_line_idx += 1

        diff_lines.append(
            DiffLine(
                operator=Operator(cur_op),
                old_line_idx=old_line_idx,
                new_line_idx=new_line_idx,
                content=content,
            )
        )

    return Diff(
        old_start_line_idx=old_start_line_idx,
        new_start_line_idx=new_start_line_idx,
        old_len=old_len,
        new_len=new_len,
        changes=diff_lines,
    )


def parse_diff_str_multi_hunk(diff_str: str) -> list[Diff]:
    """Parse a diff string consisting of multiple hunks"""
    diffs = []
    current_hunk_lines = []

    diff_str_lines = iter(diff_str.splitlines(keepends=True))

    # Remove git diff junk
    clean_diff_str_lines = []
    for diff_str_line in diff_str_lines:
        if diff_str_line.startswith("diff --git"):
            continue

        if diff_str_line.startswith("index "):
            continue

        if diff_str_line.startswith("---"):
            continue

        if diff_str_line.startswith("+++"):
            continue

        clean_diff_str_lines.append(diff_str_line)

    diff_str_lines = clean_diff_str_lines

    for line in diff_str_lines:
        if DIFF_HEADER_PTRN.match(line):
            if len(current_hunk_lines) > 0:
                diffs.append(parse_diff_str_single_hunk("".join(current_hunk_lines)))
                current_hunk_lines = []
        elif (len(diffs) == 0) and (len(current_hunk_lines) == 0):
            # Skip lines before the header of the first hunk
            continue
        current_hunk_lines.append(line)

    # Process last hunk
    if len(current_hunk_lines) > 0:
        diffs.append(parse_diff_str_single_hunk("".join(current_hunk_lines)))

    return diffs


def make_diff_header(diff: Diff) -> str:
    header = f"@@ -{diff.old_start_line_idx + 1},{diff.old_len} +{diff.new_start_line_idx + 1},{diff.new_len} @@\n"
    return header


def wait(secs):
    def decorator(func):
        def wrapper(*args, **kwargs):
            time.sleep(secs)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_language_from_path(file_path: str) -> str:
    """
    Maps a file path to its corresponding language identifier for syntax highlighting.

    Args:
        file_path: Path to the file

    Returns:
        The language identifier string suitable for syntax highlighting
    """
    extension_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".rs": "rust",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".md": "markdown",
        ".sql": "sql",
        ".kt": "kotlin",
        ".swift": "swift",
        ".r": "r",
        ".scala": "scala",
        ".pl": "perl",
        ".lua": "lua",
        ".ex": "elixir",
        ".exs": "elixir",
        ".hs": "haskell",
        ".fs": "fsharp",
        ".xml": "xml",
        ".cs": "csharp",
    }

    ext = file_path.suffix
    return extension_map.get(ext, "text")
