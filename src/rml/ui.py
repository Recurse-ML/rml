import logging
from typing import Any, Callable
import rich
from rich.console import group, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.spinner import Spinner
from rich.panel import Panel
from rich.syntax import Syntax
from rich.style import Style
from rich.rule import Rule


from collections import defaultdict

from enum import Enum
from plumbum import local

from rml.datatypes import Comment

from rml.utils import parse_diff_str_multi_hunk, make_diff_header


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
        console: rich.console.Console,
        logger: logging.Logger,
        inputs: dict = {},
        accumulate_outputs: bool = False,
    ):
        """
        steps: dict of step_id -> (step name, executor function)
        global_args: any kwargs to pass to each executor
        """
        self.steps = steps
        self.inputs = inputs
        self.console = console
        self.logger = logger
        self.accumulate_outputs = accumulate_outputs

    def render(self):
        table = Table.grid(padding=(0, 1))
        for step in self.steps:
            table.add_row(step.render())
        return Panel(table, title="Workflow", border_style="cyan")

    def run(self) -> dict[str, Any]:
        accumulated_output = {}
        with Live(self.render(), console=self.console, refresh_per_second=10) as live:
            for step in self.steps:
                step.set_state(StepState.PENDING)
                live.update(self.render())

                try:
                    # Merge previous outputs and global args
                    kwargs = {**accumulated_output, **self.inputs}
                    result = step.func(**kwargs)
                    step.output = result or {}
                    if self.accumulate_outputs:
                        collision_keys = set(accumulated_output).intersection(
                            step.output
                        )
                        if collision_keys:
                            raise ValueError(
                                f"Step '{step.name}' tried to overwrite keys already set: {collision_keys}"
                            )

                        accumulated_output.update(step.output)
                    else:
                        accumulated_output = step.output
                    step.set_state(StepState.DONE)
                except Exception as e:
                    step.set_state(StepState.FAIL)
                    live.update(self.render())
                    self.logger.error(f"Step '{step.name}' failed")
                    raise e

                live.update(self.render())

        self.console.clear()
        self.console.print("[bold green]✅ Workflow finished.[/]")
        return accumulated_output


@group()
def render_comment(comment: Comment, logger: logging.Logger, use_ruler: bool = False):
    window_size = 50

    panel = Panel(
        comment.body,
        title=f"{comment.relative_path}:{comment.line_no}",
        style=Style(bold=True, bgcolor="black"),
    )
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
        logger.warning("Found a comment with no underlying diff")
        yield panel
        return

    assert len(diffs_with_comment) == 1, (
        "Found multiple diffs containing the same lines, this should not happen"
    )

    diff = diffs_with_comment[0]
    diff_str_lines = []
    diff_header = make_diff_header(diff)

    curr_old_line = diff.old_start_line_idx + 1
    curr_new_line = diff.new_start_line_idx + 1

    for change in diff.changes:
        diff_str_lines.append(f"{change.operator.value}{change.content}")

        if change.old_line_idx is not None:
            curr_old_line += 1
        if change.new_line_idx is not None:
            if curr_new_line == comment.line_no:
                syntax = Syntax(
                    "".join([diff_header] + diff_str_lines[-window_size:]),
                    "diff",
                    theme="ansi_dark",
                )
                yield syntax
                yield panel
                diff_str_lines = []

            curr_new_line += 1

    if diff_str_lines:
        syntax = Syntax(
            "".join(diff_str_lines[:window_size]), "diff", theme="ansi_dark"
        )
        yield syntax

    if comment.documentation_url is not None:
        yield Text(f"More info: {comment.documentation_url}\n")
    if use_ruler:
        yield Rule(style=Style(color="grey50"))


def render_comments(
    comments: list[Comment], console: rich.console.Console, logger: logging.Logger
):
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
