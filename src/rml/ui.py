from pathlib import Path
import re
import rich
from logging import Logger
from typing import Any, Callable, Optional
from rich.console import Group, Console
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.spinner import Spinner
from rich.panel import Panel
from rich.syntax import Syntax
from rich.style import Style
from rich.rule import Rule
from rich.markdown import Markdown

from collections import defaultdict

from enum import Enum
from plumbum import local

from rml.datatypes import APICommentResponse
from rml.package_logger import logger

from rml.utils import (
    enrich_bc_markdown_with_source,
    parse_diff_str_multi_hunk,
    make_diff_header,
    get_language_from_path,
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


def render_comment(
    comment: APICommentResponse,
    logger: Logger,
    use_ruler: bool = False,
    context_window: int = 50,
) -> Group:
    """
    Renders a comment with diffs around the comment body.
    For breaking change comments, renders the markdown formatted message without diffs.
    Args:
        - `context_window` controls how much context of the diff is displayed around each comment on both the sides.
        - `use_ruler` draws a horizontal ruler below the comment if set.
    Returns:
        A Group of UI elements to be rendered.
    """
    ui_elements = []

    # Breaking change comment - render only the markdown content without diffs
    if comment.reference_locations is not None:
        markdown_content = enrich_bc_markdown_with_source(comment)
        if markdown_content is None:
            logger.warning(
                f"Failed to enrich breaking change comment at {comment.relative_path}:{comment.line_no},"
                "not displaying the comment"
            )
            comment_panel = None
        else:
            comment_panel = Panel(
                Markdown(markdown_content),
                title=f"{comment.relative_path}:{comment.line_no}",
                style=Style(bold=True, bgcolor="black"),
            )
            ui_elements.append(comment_panel)

    # Regular comment - render with diffs
    else:
        comment_panel = Panel(
            comment.body,
            title=f"{comment.relative_path}:{comment.line_no}",
            style=Style(bold=True, bgcolor="black"),
        )

        if comment_panel is not None:
            ui_elements.append(comment_panel)

        # TODO: get git diff from API.
        git_diff = local["git"]["diff", comment.relative_path]()
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
        else:
            assert len(diffs_with_comment) == 1, (
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

            pre_comment_syntax = make_comment_syntax(
                lines=[diff_header] + diff_str_lines_before_comment[-context_window:]
            )
            ui_elements.insert(0, pre_comment_syntax)

            if diff_str_lines_after_comment:
                post_comment_syntax = make_comment_syntax(
                    lines=diff_str_lines_after_comment[:context_window],
                )
                ui_elements.append(post_comment_syntax)

    # For both breaking change and regular comments, add optional elements
    if comment.documentation_url is not None:
        ui_elements.append(Text(f"More info: {comment.documentation_url}\n"))
    if use_ruler:
        ui_elements.append(Rule(style=Style(color="grey50")))
    return Group(*ui_elements)


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
                render_comment(comment, logger=logger, use_ruler=use_ruler)
                for comment, use_ruler in zip(file_comments, use_rulers)
            )
        )
        file_panel = Panel(file_group, title=f"[bold white on blue] {rel_path} [/]")

        console.print(file_panel)
