from collections import defaultdict
from enum import Enum
from logging import Logger
from typing import Any, Callable

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from rml.datatypes import APICommentResponse
from rml.utils import (
    enrich_bc_ref_locations_with_source,
    make_diff_header,
    parse_diff_str_multi_hunk,
)


class StepState(Enum):
    TODO = "TODO"
    PENDING = "PENDING"
    DONE = "DONE"
    FAIL = "FAIL"


class Step:
    def __init__(self, name: str, func: Callable[..., dict]):
        self.name = name
        self.func = func
        self.state = StepState.TODO
        self.output = {}

    def set_state(self, state: StepState):
        self.state = state

    def render(self):
        table = Table.grid(padding=(0, 1))
        table.add_column(width=4)  # Column for symbol/spinner
        table.add_column(ratio=1)  # Column for label

        if self.state == StepState.TODO:
            symbol = Text("[ ]", style="grey50")
            label = Text(self.name, style="grey50")
            table.add_row(symbol, label)

        elif self.state == StepState.PENDING:
            spinner = Spinner("dots", style="yellow")
            label = Text(self.name, style="yellow")
            table.add_row(spinner, label)

        elif self.state == StepState.DONE:
            symbol = Text("[✔]", style="bold green")
            label = Text(self.name, style="bold green")
            table.add_row(symbol, label)

        elif self.state == StepState.FAIL:
            symbol = Text("[✘]", style="bold red")
            label = Text(self.name, style="bold red")
            table.add_row(symbol, label)

        return table


class Workflow:
    def __init__(
        self,
        steps: list[Step],
        console: Console,
        logger: Logger,
        inputs: dict = {},
    ):
        """
        Creates a workflow of linear steps to be executed in order.
        When `run` is called, the outputs of each step are passed as inputs to the next step along with the
        global `inputs` passed to every step.
        Args:
            steps: dict of step_id -> (step name, executor function)
            inputs: any kwargs to pass to each executor
        """
        self.steps = steps
        self.inputs = inputs
        self.console = console
        self.logger = logger

    def render(self):
        table = Table.grid(padding=(0, 1))
        for step in self.steps:
            table.add_row(step.render())
        return Panel(table, title="Workflow", border_style="cyan")

    def run(self) -> dict[str, Any]:
        with Live(self.render(), console=self.console, refresh_per_second=10) as live:
            prev_output = {}
            for step in self.steps:
                step.set_state(StepState.PENDING)
                live.update(self.render())

                try:
                    # Merge previous outputs and global args
                    kwargs = {**prev_output, **self.inputs}
                    result = step.func(**kwargs)
                    step.output = result or {}
                    prev_output = step.output
                    step.set_state(StepState.DONE)
                except Exception as e:
                    step.set_state(StepState.FAIL)
                    live.update(self.render())
                    self.logger.error(f"Step '{step.name}' failed")
                    raise e

                live.update(self.render())

        self.console.clear()
        self.console.print("[bold green]✅ Analysis finished.[/]")
        return prev_output


def make_comment_syntax(lines: list[str]) -> Syntax:
    return Syntax(
        "".join(lines),
        "diff",
        theme="ansi_dark",
    )


def render_breaking_change(
    comment: APICommentResponse,
    logger: Logger,
    context_window: int = 50,
) -> Group:
    """
    Renders a breaking change comment with:
    1. The diff showing the breaking change
    2. The explanation of why it breaks
    3. The affected locations
    """
    # TODO: should read diff from the response
    comment_diff = create_comment_diff(comment, logger, context_window)

    comment_md = enrich_bc_ref_locations_with_source(comment)
    if comment_md is None:
        logger.warning(
            f"Failed to enrich reference locations for comment at {comment.relative_path}:{comment.line_no},"
            "not displaying the comment"
        )
        return None

    panel_content = Group(*comment_diff, Markdown(comment_md))

    return Panel(
        panel_content,
        title=f"{comment.relative_path}:{comment.line_no}",
        style=Style(bold=True, bgcolor="black"),
    )


def render_regular_comment(
    comment: APICommentResponse,
    logger: Logger,
    context_window: int = 50,
) -> Group:
    """
    Renders a regular comment with:
    1. The diff showing the context
    2. The comment body
    """
    # TODO: should read diff from the response
    comment_diff = create_comment_diff(comment, logger, context_window)
    panel_content = Group(*comment_diff, Text(comment.body))
    return Panel(
        panel_content,
        title=f"{comment.relative_path}:{comment.line_no}",
        style=Style(bold=True, bgcolor="black"),
    )


def render_comment(
    comment: APICommentResponse,
    logger: Logger,
    use_ruler: bool = False,
    context_window: int = 50,
) -> Group:
    """
    Args:
        - `comment` the comment to render
        - `logger` the logger to use
        - `use_ruler` draws a horizontal ruler below the comment if set.
        - `context_window` controls how much context of the diff is displayed around each comment on both the sides.
    Returns:
        A Group of UI elements to be rendered.
    """
    ui_elements = []

    if comment.reference_locations is not None:
        comment_panel = render_breaking_change(comment, logger, context_window)
    else:
        comment_panel = render_regular_comment(comment, logger, context_window)

    if comment_panel is not None:
        ui_elements.append(comment_panel)

    if use_ruler:
        ui_elements.append(Rule(style=Style(color="grey50")))

    return Group(*ui_elements)


def create_comment_diff(
    comment: APICommentResponse,
    logger: Logger,
    context_window: int = 50,
) -> list[Syntax]:
    """
    Helper function to get the diff to which the comment belongs.
    Returns a list of Syntax elements to be rendered.
    """
    elements = []
    git_diff = comment.diff_str
    parsed_output = parse_diff_str_multi_hunk(git_diff)

    diffs_with_comment = []

    for diff in parsed_output:
        diff_new_start_line_no = diff.new_start_line_idx + 1
        diff_new_end_line_no = diff_new_start_line_no + diff.new_len
        if diff_new_start_line_no <= comment.line_no < diff_new_end_line_no:
            diffs_with_comment.append(diff)

    if len(diffs_with_comment) == 0:
        logger.warning(
            f"Found a comment {comment.relative_path}:{comment.line_no} with no underlying diff"
        )
        return elements

    if len(diffs_with_comment) > 1:
        logger.error(
            "Found multiple diffs containing the same lines, this should not happen"
        )
        raise AssertionError(
            "Found multiple diffs containing the same lines, this should not happen"
        )

    diff = diffs_with_comment[0]
    diff_header = make_diff_header(diff)
    diff_str_lines_before_comment = []
    diff_str_lines_after_comment = []

    curr_old_line = diff.old_start_line_idx + 1
    curr_new_line = diff.new_start_line_idx + 1

    for change in diff.changes:
        if curr_new_line <= comment.line_no:
            diff_str_lines_before_comment.append(
                f"{change.operator.value}{change.content}"
            )
        else:
            diff_str_lines_after_comment.append(
                f"{change.operator.value}{change.content}"
            )

        if change.old_line_idx is not None:
            curr_old_line += 1
        if change.new_line_idx is not None:
            curr_new_line += 1

    if diff_str_lines_before_comment or diff_str_lines_after_comment:
        full_diff_lines = [diff_header]
        if diff_str_lines_before_comment:
            full_diff_lines.extend(diff_str_lines_before_comment[-context_window:])
        if diff_str_lines_after_comment:
            full_diff_lines.extend(diff_str_lines_after_comment[:context_window])

        diff_syntax = make_comment_syntax(lines=full_diff_lines)
        diff_panel = Panel(
            diff_syntax,
            style=Style(
                bgcolor="#1c1c1c"
            ),  # Using 'black' here doesn't work for some reason
            border_style="dim",  # dim border for better readability
            padding=(0, 1),  # Horizontal padding for better readability
        )
        elements.append(diff_panel)

    return elements


def render_comments(
    comments: list[APICommentResponse], console: Console, logger: Logger
):
    """
    Given a list of comments to be rendered, groups them by the file name, rendering each file in its own panel
    and renders the comments of that file in order along with their diffs.
    """
    path_comment_map = defaultdict(list)

    for comment in comments:
        path_comment_map[comment.relative_path].append(comment)

    for rel_path, file_comments in path_comment_map.items():
        file_comments = sorted(file_comments, key=lambda x: x.line_no)
        use_rulers = [True] * len(file_comments)
        use_rulers[-1] = False
        file_group = Group(
            *(
                render_comment(
                    comment, logger=logger, use_ruler=use_ruler, context_window=3
                )
                for comment, use_ruler in zip(file_comments, use_rulers)
            )
        )
        file_panel = Panel(file_group, title=f"[bold white on blue] {rel_path} [/]")

        console.print(file_panel)
