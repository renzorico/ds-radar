"""
ds-radar interactive review cockpit
Usage: python scripts/dashboard.py
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame

from job_data import FILTER_OPTIONS, JobRecord, filter_records, load_job_records, update_tracker_status

VISIBLE_ROWS = 18
FILTER_LABELS = {
    "all": "1 All",
    "b_plus": "2 B+",
    "sponsorship_fail": "3 Sponsorship Fail",
    "linkedin_only": "4 LinkedIn",
    "ready": "5 Ready",
}
STATUS_ACTIONS = {
    "u": "evaluated",
    "v": "cv_ready",
    "a": "applied",
    "k": "skipped",
}
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class DashboardState:
    sort_by: str = "date"
    filter_name: str = "all"
    selected_index: int = 0
    message: str = ""
    apply_dry_run: bool = False
    pending_apply_url: str = ""

    def __post_init__(self) -> None:
        self.records = load_job_records(sort_by=self.sort_by)
        self._clamp_index()

    @property
    def filtered_records(self) -> list[JobRecord]:
        return filter_records(self.records, self.filter_name)

    def current_record(self) -> JobRecord | None:
        rows = self.filtered_records
        if not rows:
            return None
        self._clamp_index()
        return rows[self.selected_index]

    def _clamp_index(self) -> None:
        rows = self.filtered_records
        if not rows:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index, len(rows) - 1))

    def move(self, delta: int) -> None:
        self.selected_index += delta
        self._clamp_index()

    def set_filter(self, filter_name: str) -> None:
        self.filter_name = filter_name
        self.selected_index = 0
        self._clamp_index()
        self.message = f"Filter: {FILTER_LABELS[filter_name]}"

    def reload(self) -> None:
        current_url = self.current_record().url if self.current_record() else ""
        self.records = load_job_records(sort_by=self.sort_by)
        rows = self.filtered_records
        if current_url:
            for index, record in enumerate(rows):
                if record.url == current_url:
                    self.selected_index = index
                    break
        self._clamp_index()
        self.message = "Reloaded tracker and filesystem artifacts."

    def set_status(self, status: str) -> None:
        record = self.current_record()
        if record is None:
            self.message = "No row selected."
            return
        if update_tracker_status(record.url, status):
            self.reload()
            self.message = f"Status updated: {record.company} -> {status}"
        else:
            self.message = f"Status update failed for {record.company}."

    def request_apply(self) -> None:
        record = self.current_record()
        if record is None:
            self.message = "No row selected."
            return
        self.pending_apply_url = record.url
        suffix = " --dry-run" if self.apply_dry_run else ""
        self.message = f"Apply to {record.company} — {record.role}? [y/N]{suffix}"

    def clear_apply_request(self) -> None:
        self.pending_apply_url = ""


def build_apply_command(url: str, dry_run: bool) -> list[str]:
    command = [sys.executable, "scripts/apply.py"]
    if dry_run:
        command.append("--dry-run")
    command.append(url)
    return command


def run_apply_command(url: str, dry_run: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_apply_command(url, dry_run),
        cwd=REPO_ROOT,
        text=True,
        check=False,
    )


def startup_log(state: DashboardState) -> str:
    counts = {name: len(filter_records(state.records, name)) for name in FILTER_OPTIONS}
    return (
        "[dashboard] loaded tracker review cockpit\n"
        f"[dashboard] rows={len(state.records)} sort={state.sort_by} "
        f"filters=all:{counts['all']} b_plus:{counts['b_plus']} "
        f"sponsorship_fail:{counts['sponsorship_fail']} linkedin:{counts['linkedin_only']} "
        f"ready:{counts['ready']}"
    )


def format_path(path_text: str) -> str:
    return path_text if path_text else "—"


def render_table(state: DashboardState) -> list[tuple[str, str]]:
    rows = state.filtered_records
    fragments: list[tuple[str, str]] = []
    header = (
        f"{'DATE':<10} {'G':<2} {'SRC':<8} {'JD':<4} {'SP':<4} "
        f"{'CV':<3} {'OFE':<3} {'CON':<3} {'COMPANY':<18} ROLE"
    )
    fragments.append(("class:header", header))
    fragments.append(("", "\n"))

    if not rows:
        fragments.append(("class:muted", "No rows match the current filter."))
        return fragments

    start = max(0, state.selected_index - (VISIBLE_ROWS // 2))
    end = min(len(rows), start + VISIBLE_ROWS)
    start = max(0, end - VISIBLE_ROWS)

    for index in range(start, end):
        record = rows[index]
        style = "class:selected" if index == state.selected_index else ""
        prefix = ">" if index == state.selected_index else " "
        line = (
            f"{prefix} {record.date:<10} {record.grade:<2} {record.source:<8} {record.jd_src:<4} "
            f"{record.spons:<4} {record.cv:<3} {record.ofe:<3} {record.con:<3} "
            f"{record.company[:18]:<18} {record.role[:34]}"
        )
        fragments.append((style, line))
        fragments.append(("", "\n"))

    fragments.append(
        (
            "class:muted",
            f"Rows {start + 1}-{end} of {len(rows)} | selected {state.selected_index + 1}",
        )
    )
    return fragments


def render_details(state: DashboardState) -> list[tuple[str, str]]:
    record = state.current_record()
    if record is None:
        return [("class:muted", "No record selected.")]

    lines = [
        ("class:title", f"{record.company} | {record.role}\n"),
        ("", f"Grade: {record.grade} | Score: {record.score} | Status: {record.status}\n"),
        ("", f"Source: {record.source} | JD: {record.jd_src} | Sponsorship: {record.spons}\n"),
        ("", f"Ready to apply: {'yes' if record.ready_to_apply else 'no'}\n"),
        ("", f"URL: {record.url}\n\n"),
        ("class:label", "Paths\n"),
        ("", f"Eval: {format_path(record.eval_path)}\n"),
        ("", f"CV: {format_path(record.cv_path)}\n"),
        ("", f"Oferta: {format_path(record.oferta_path)}\n"),
        ("", f"Outreach: {format_path(record.outreach_path)}\n\n"),
        ("class:label", "Excerpt\n"),
        ("", f"{record.eval_excerpt or 'No summary excerpt available.'}\n\n"),
        ("class:label", "Actions\n"),
        ("", "e eval | c cv | o outreach | p apply | r reload\n"),
        ("", "u evaluated | v cv_ready | a applied | k skipped\n"),
        ("", "1-5 filters | up/down move | y/n confirm apply | q quit\n"),
    ]
    return lines


def render_header(state: DashboardState) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = [("class:title", "ds-radar cockpit  ")]
    for name in FILTER_OPTIONS:
        style = "class:filter_active" if state.filter_name == name else "class:filter"
        parts.append((style, FILTER_LABELS[name]))
        parts.append(("", "  "))
    return parts


def render_footer(state: DashboardState) -> list[tuple[str, str]]:
    return [("class:footer", state.message or "Ready.")]


def open_path_in_terminal(path_text: str) -> None:
    if not path_text:
        return

    path = Path(path_text)
    full_path = path if path.is_absolute() else (Path(__file__).resolve().parent.parent / path)
    if not full_path.exists():
        return

    editor = os.environ.get("EDITOR")
    if editor:
        command = shlex.split(editor) + [str(full_path)]
    else:
        command = ["less", str(full_path)]
    subprocess.run(command, check=False)


def build_dashboard_app(state: DashboardState) -> Application:
    header_control = FormattedTextControl(lambda: render_header(state))
    table_control = FormattedTextControl(lambda: render_table(state), focusable=False)
    detail_control = FormattedTextControl(lambda: render_details(state), focusable=False)
    footer_control = FormattedTextControl(lambda: render_footer(state))

    bindings = KeyBindings()

    @bindings.add("q")
    def _quit(event) -> None:
        event.app.exit()

    @bindings.add("up")
    def _up(event) -> None:
        state.move(-1)
        event.app.invalidate()

    @bindings.add("down")
    def _down(event) -> None:
        state.move(1)
        event.app.invalidate()

    @bindings.add("pageup")
    def _page_up(event) -> None:
        state.move(-VISIBLE_ROWS)
        event.app.invalidate()

    @bindings.add("pagedown")
    def _page_down(event) -> None:
        state.move(VISIBLE_ROWS)
        event.app.invalidate()

    @bindings.add("home")
    def _home(event) -> None:
        state.selected_index = 0
        event.app.invalidate()

    @bindings.add("end")
    def _end(event) -> None:
        state.selected_index = len(state.filtered_records) - 1
        state._clamp_index()
        event.app.invalidate()

    for key, filter_name in zip(["1", "2", "3", "4", "5"], FILTER_OPTIONS):
        @bindings.add(key)
        def _set_filter(event, filter_name=filter_name) -> None:
            state.set_filter(filter_name)
            event.app.invalidate()

    @bindings.add("r")
    def _reload(event) -> None:
        state.reload()
        event.app.invalidate()

    @bindings.add("p")
    def _prompt_apply(event) -> None:
        state.request_apply()
        event.app.invalidate()

    @bindings.add("y")
    def _confirm_apply(event) -> None:
        if not state.pending_apply_url:
            return
        record = state.current_record()
        if record is None or record.url != state.pending_apply_url:
            state.clear_apply_request()
            state.message = "Apply cancelled: selection changed."
            event.app.invalidate()
            return
        state.message = f"Running apply.py for {record.company}..."
        event.app.invalidate()

        def _run_apply() -> None:
            result = run_apply_command(record.url, state.apply_dry_run)
            if result.returncode == 0:
                if state.apply_dry_run:
                    state.message = f"apply.py dry-run completed for {record.company}"
                else:
                    state.set_status("applied")
            else:
                state.message = f"apply.py failed for {record.company} (exit {result.returncode})"
            state.clear_apply_request()

        run_in_terminal(_run_apply)
        event.app.invalidate()

    @bindings.add("n")
    @bindings.add("N")
    def _cancel_apply(event) -> None:
        if not state.pending_apply_url:
            return
        state.clear_apply_request()
        state.message = "Apply cancelled."
        event.app.invalidate()

    for key, status in STATUS_ACTIONS.items():
        @bindings.add(key)
        def _set_status(event, status=status) -> None:
            state.set_status(status)
            event.app.invalidate()

    @bindings.add("e")
    def _open_eval(event) -> None:
        record = state.current_record()
        if record is None or not record.eval_path:
            state.message = "No eval file for selected row."
            event.app.invalidate()
            return
        state.message = f"Opening eval: {record.eval_path}"
        event.app.invalidate()
        run_in_terminal(lambda: open_path_in_terminal(record.eval_path))

    @bindings.add("c")
    def _open_cv(event) -> None:
        record = state.current_record()
        if record is None or not record.cv_path:
            state.message = "No CV artifact for selected row."
            event.app.invalidate()
            return
        state.message = f"Opening CV: {record.cv_path}"
        event.app.invalidate()
        run_in_terminal(lambda: open_path_in_terminal(record.cv_path))

    @bindings.add("o")
    def _open_outreach(event) -> None:
        record = state.current_record()
        if record is None or not record.outreach_path:
            state.message = "No outreach artifact for selected row."
            event.app.invalidate()
            return
        state.message = f"Opening outreach: {record.outreach_path}"
        event.app.invalidate()
        run_in_terminal(lambda: open_path_in_terminal(record.outreach_path))

    root_container = HSplit(
        [
            Window(content=header_control, height=1),
            VSplit(
                [
                    Frame(Window(content=table_control, wrap_lines=False), title="Jobs", width=Dimension(weight=5)),
                    Frame(Window(content=detail_control, wrap_lines=True), title="Details", width=Dimension(weight=6)),
                ]
            ),
            Window(content=footer_control, height=1),
        ]
    )

    style = Style.from_dict(
        {
            "title": "bold ansicyan",
            "header": "bold ansiyellow",
            "label": "bold ansigreen",
            "muted": "ansibrightblack",
            "selected": "reverse",
            "filter": "ansibrightblack",
            "filter_active": "bold ansiblue",
            "footer": "reverse",
        }
    )

    return Application(
        layout=Layout(root_container),
        key_bindings=bindings,
        full_screen=True,
        style=style,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ds-radar interactive dashboard")
    parser.add_argument("--sort", default="date", choices=["date", "grade", "company", "score"])
    parser.add_argument("--filter", default="all", choices=FILTER_OPTIONS)
    parser.add_argument("--print-startup", action="store_true", help="Print startup log before launching")
    parser.add_argument("--dump-row", type=int, default=None, metavar="INDEX", help="Print one row model and exit")
    parser.add_argument("--apply-dry-run", action="store_true", help="Run apply.py --dry-run when pressing p")
    args = parser.parse_args()

    state = DashboardState(
        sort_by=args.sort,
        filter_name=args.filter,
        apply_dry_run=args.apply_dry_run,
    )
    if args.print_startup:
        print(startup_log(state))

    if args.dump_row is not None:
        rows = state.filtered_records
        if not rows:
            print("No rows available for current filter.")
            return
        index = max(0, min(args.dump_row, len(rows) - 1))
        print(rows[index].to_json())
        return

    state.message = "Keys: 1-5 filters | up/down move | e/c/o open files | p apply | u/v/a/k set status | q quit"
    app = build_dashboard_app(state)
    app.run()


if __name__ == "__main__":
    main()
