"""
ds-radar interactive review dashboard
Usage: python scripts/dashboard.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import shorten

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

try:
    from job_data import (
        FILTER_OPTIONS,
        JobRecord,
        extract_rejection_reason,
        filter_records,
        load_dashboard_records,
        load_dashboard_record_detail,
        load_dashboard_record_summary,
        normalize_record_status,
        update_tracker_status,
        upsert_rejection_reason,
    )
except ImportError:
    from scripts.job_data import (
        FILTER_OPTIONS,
        JobRecord,
        extract_rejection_reason,
        filter_records,
        load_dashboard_records,
        load_dashboard_record_detail,
        load_dashboard_record_summary,
        normalize_record_status,
        update_tracker_status,
        upsert_rejection_reason,
    )

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_STATE_FILE = REPO_ROOT / ".dashboard.state.json"

GRADE_STYLES = {
    "A": "bold green",
    "B": "bold cyan",
    "C": "bold yellow",
    "D": "bold red",
    "F": "bold red",
}

STATUS_STYLES = {
    "cv_ready": "bold white",
    "applied": "bold cyan",
    "callback": "bold magenta",
    "interview": "bold green",
    "rejected": "dim red",
    "skipped": "dim",
}

FILTER_LABELS = {
    "all": "All",
    "a_plus": "A+",
    "b_plus": "B+",
    "to_apply": "To apply",
    "applied": "Applied",
    "callback": "Callback",
    "interview": "Interview",
    "rejected": "Rejected",
}

STATUS_SORT_ORDER = {
    "cv_ready": 0,
    "applied": 1,
    "callback": 2,
    "interview": 3,
    "rejected": 4,
    "skipped": 5,
    "": 6,
}

def load_dashboard_session() -> dict:
    if DASHBOARD_STATE_FILE.exists():
        try:
            return json.loads(DASHBOARD_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"filter_name": "all", "selected_index": 0}


def save_dashboard_session(filter_name: str, selected_index: int) -> None:
    DASHBOARD_STATE_FILE.write_text(
        json.dumps({"filter_name": filter_name, "selected_index": selected_index}, indent=2),
        encoding="utf-8",
    )


HELP_TEXT = """\
[bold cyan]Filters[/]
  [bold]1[/] All      [bold]2[/] A+       [bold]3[/] B+       [bold]4[/] To apply
  [bold]5[/] Applied  [bold]6[/] Callback [bold]7[/] Interview [bold]8[/] Rejected

[bold cyan]Movement[/]
  [bold]j / k[/] move     [bold]h / l[/] prev / next tab     [bold]g / G[/] top / bottom     [bold]/[/] search

[bold cyan]Status[/]
  [bold]a[/] applied   [bold]c[/] callback   [bold]i[/] interview
  [bold]x[/] skipped   [bold]r[/] rejected  [bold]f[/] sponsor fail  [bold]s[/] seniority fail

[bold cyan]Other[/]
  [bold]w[/] oferta   [bold]o[/] outreach   [bold]R[/] reload   [bold]Ctrl+P[/] options   [bold]q[/] quit
"""


class HelpScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 72;
        background: $surface;
        border: solid white;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("ctrl+p", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold]ds-radar shortcuts[/]")
            yield Static(HELP_TEXT)


class ModelPromptScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    ModelPromptScreen {
        align: center middle;
    }
    ModelPromptScreen > Vertical {
        width: 72;
        background: $surface;
        border: solid white;
        padding: 1 2;
    }
    #model-input {
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
    ]

    def __init__(self, initial_value: str = "") -> None:
        super().__init__()
        self._initial_value = initial_value

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold]Select model[/]")
            yield Static("[dim]Example: gpt-5.4-mini or claude-haiku-4-5-20251001[/]")
            yield Input(value=self._initial_value, placeholder="gpt-5.4-mini", id="model-input")

    def on_mount(self) -> None:
        self.query_one("#model-input", Input).focus()

    @on(Input.Submitted, "#model-input")
    def on_submit(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.dismiss(value or None)


class FilterBar(Static):
    active_filter: reactive[str] = reactive("all")
    job_count: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    FilterBar {
        height: 1;
        padding: 0 1;
    }
    """

    def render(self) -> Text:
        text = Text()
        for index, name in enumerate(FILTER_OPTIONS, start=1):
            label = f"{index}:{FILTER_LABELS[name]}"
            style = "bold reverse" if name == self.active_filter else "dim"
            text.append(label, style=style)
            text.append("  ")
        text.append(f"{self.job_count} rows", style="dim")
        return text


class ShortcutBar(Static):
    DEFAULT_CSS = """
    ShortcutBar {
        height: 1;
        padding: 0 1;
    }
    """

    def render(self) -> Text:
        return Text(
            "h/l tabs  a applied  x skipped  c callback  i interview  r rejected  f sponsor fail  s seniority fail  w oferta  o outreach  q quit  R reload  / search  ^p options",
            style="dim",
        )


def format_status(record: JobRecord) -> str:
    reason = extract_rejection_reason(record.notes)
    if record.status != "rejected":
        return record.status or "---"
    if reason == "sponsorship_fail":
        return "rejected:f"
    if reason == "seniority_fail":
        return "rejected:s"
    return "rejected"


def compact_text(value: str, width: int) -> str:
    text = " ".join((value or "").split())
    if not text:
        return "---"
    return shorten(text, width=width, placeholder="...")


def compact_url(value: str, width: int = 44) -> str:
    return compact_text(value, width)


def compact_path(value: str, width: int = 96) -> str:
    return compact_text(value, width)


def display_path(value: str) -> str:
    return value.strip() or "---"


class DetailPane(Static):
    record: reactive[JobRecord | None] = reactive(None)

    DEFAULT_CSS = """
    DetailPane {
        padding: 1;
        height: 100%;
        border: solid white;
        overflow-x: hidden;
        overflow-y: auto;
    }
    """

    def watch_record(self, record: JobRecord | None) -> None:
        if record is None:
            self.update("[dim]No role selected[/]")
            return

        rejection_reason = extract_rejection_reason(record.notes)
        grade_style = GRADE_STYLES.get(record.grade, "bold")
        status_style = STATUS_STYLES.get(record.status, "bold")
        lines = [
            f"[bold]{record.company}[/]",
            f"[dim]{record.role}[/]",
            "",
            f"[bold]grade[/] [{grade_style}]{record.grade}[/]   [bold]score[/] {record.score}",
            f"[bold]status[/] [{status_style}]{format_status(record)}[/]",
            f"[bold]date[/] {record.date}",
            f"[bold]jd[/] {record.jd_src}   [bold]sponsorship[/] {record.spons}",
            "",
            "[bold cyan]Link[/]",
            compact_url(record.url, 64),
        ]
        lines.extend(
            [
                "",
                "[bold cyan]Files[/]",
                f"[bold]eval[/] {display_path(record.eval_path)}",
                f"[bold]cv[/] {display_path(record.cv_path)}",
                f"[bold]oferta[/] {display_path(record.oferta_path)}",
                f"[bold]outreach[/] {display_path(record.outreach_path)}",
            ]
        )
        if record.eval_excerpt:
            lines.extend(["", "[bold cyan]Summary[/]", record.eval_excerpt])
        clean_notes = upsert_rejection_reason(record.notes, "")
        if clean_notes:
            lines.extend(["", "[bold cyan]Notes[/]", clean_notes])
        if rejection_reason == "sponsorship_fail":
            lines.extend(["", "[bold red]Reject reason:[/] sponsorship"])
        elif rejection_reason == "seniority_fail":
            lines.extend(["", "[bold red]Reject reason:[/] seniority"])
        self.update("\n".join(lines))


class DashboardApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #search-bar {
        height: 1;
        display: none;
    }
    #search-bar.visible {
        display: block;
    }
    #main-area {
        height: 1fr;
        overflow-x: hidden;
        overflow-y: hidden;
    }
    #job-table {
        width: 65%;
        height: 100%;
        border: solid white;
        overflow-x: hidden;
        overflow-y: hidden;
    }
    #detail-pane {
        width: 35%;
        height: 100%;
        overflow-x: hidden;
        overflow-y: auto;
    }
    DataTable {
        height: 100%;
        overflow-x: hidden;
        overflow-y: hidden;
    }
    DataTable > .datatable--cursor {
        background: white;
        color: black;
    }
    """

    TITLE = "ds-radar"
    SUB_TITLE = "dashboard"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+p", "options", "Options"),
        Binding("R", "reload", "Reload"),
        Binding("slash", "search", "Search"),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("h", "prev_tab", show=False),
        Binding("l", "next_tab", show=False),
        Binding("g", "cursor_top", show=False),
        Binding("G", "cursor_bottom", show=False),
        Binding("a", "status_applied", show=False),
        Binding("x", "status_skipped", show=False),
        Binding("c", "status_callback", show=False),
        Binding("i", "status_interview", show=False),
        Binding("r", "status_rejected", show=False),
        Binding("f", "status_sponsor_fail", show=False),
        Binding("s", "status_seniority_fail", show=False),
        Binding("w", "generate_oferta", show=False),
        Binding("o", "generate_outreach", show=False),
        Binding("1", "filter_1", show=False),
        Binding("2", "filter_2", show=False),
        Binding("3", "filter_3", show=False),
        Binding("4", "filter_4", show=False),
        Binding("5", "filter_5", show=False),
        Binding("6", "filter_6", show=False),
        Binding("7", "filter_7", show=False),
        Binding("8", "filter_8", show=False),
    ]

    sort_by: reactive[str] = reactive("date")
    filter_name: reactive[str] = reactive("all")
    search_query: reactive[str] = reactive("")

    def __init__(
        self,
        sort_by: str = "date",
        filter_name: str = "all",
        initial_index: int = 0,
    ) -> None:
        super().__init__()
        self.sort_by = sort_by
        self.filter_name = filter_name
        self._initial_index = initial_index
        self._all_records: list[JobRecord] = []
        self._filtered: list[JobRecord] = []
        self._detail_cache: dict[str, JobRecord] = {}
        self._search_active = False
        self._header_sort_key = sort_by
        self._header_sort_reverse = sort_by == "date"
        self._model_override = os.environ.get("MODEL_OVERRIDE", "").strip()
        self.theme = "catppuccin-macchiato"

    def compose(self) -> ComposeResult:
        yield FilterBar(id="filter-bar")
        yield Input(placeholder="search company, role, status", id="search-bar")
        with Horizontal(id="main-area"):
            yield DataTable(id="job-table", cursor_type="row", zebra_stripes=False)
            yield DetailPane(id="detail-pane")
        yield ShortcutBar(id="shortcut-bar")

    def on_mount(self) -> None:
        table = self.query_one("#job-table", DataTable)
        detail = self.query_one(DetailPane)
        table.show_horizontal_scrollbar = False
        table.show_vertical_scrollbar = False
        detail.show_horizontal_scrollbar = False
        detail.show_vertical_scrollbar = False
        table.add_column("G", width=3, key="grade")
        table.add_column("Status", width=12, key="status")
        table.add_column("Company", width=22, key="company")
        table.add_column("Role", width=49, key="role")
        self._load_data()
        if self._filtered:
            table.move_cursor(row=min(self._initial_index, len(self._filtered) - 1))
        self._update_detail()
        table.focus()

    def _load_data(self) -> None:
        self._all_records = load_dashboard_records(sort_by=self.sort_by)
        self._apply_filter()

    def _apply_filter(self) -> None:
        rows = filter_records(self._all_records, self.filter_name)
        if self.search_query:
            query = self.search_query.lower()
            rows = [
                row for row in rows
                if query in row.company.lower()
                or query in row.role.lower()
                or query in format_status(row).lower()
            ]
        rows = self._sort_filtered_records(rows)
        self._filtered = rows
        self._populate_table()

    def _sort_filtered_records(self, rows: list[JobRecord]) -> list[JobRecord]:
        def score_value(record: JobRecord) -> float:
            try:
                return float(record.score)
            except (TypeError, ValueError):
                return -1.0

        def key_fn(record: JobRecord):
            if self._header_sort_key == "grade":
                return (record.grade, record.company.lower(), record.role.lower())
            if self._header_sort_key == "status":
                return (
                    STATUS_SORT_ORDER.get(record.status or "", 999),
                    record.company.lower(),
                    record.role.lower(),
                )
            if self._header_sort_key == "company":
                return (record.company.lower(), record.role.lower())
            if self._header_sort_key == "role":
                return (record.role.lower(), record.company.lower())
            if self._header_sort_key == "score":
                return (score_value(record), record.company.lower())
            return (record.date, record.company.lower(), record.role.lower())

        return sorted(rows, key=key_fn, reverse=self._header_sort_reverse)

    def _populate_table(self) -> None:
        table = self.query_one("#job-table", DataTable)
        current_record = self._current_record() if table.row_count else None
        selected_url = current_record.url if current_record else ""
        table.clear()
        restore_index = 0

        for index, record in enumerate(self._filtered):
            if selected_url and record.url == selected_url:
                restore_index = index
            table.add_row(
                Text(record.grade, style=GRADE_STYLES.get(record.grade, "")),
                Text(format_status(record), style=STATUS_STYLES.get(record.status, "")),
                Text(compact_text(record.company, 22)),
                Text(compact_text(record.role, 49)),
            )

        if table.row_count:
            table.move_cursor(row=min(restore_index, table.row_count - 1))
        else:
            self.query_one(DetailPane).record = None

        filter_bar = self.query_one(FilterBar)
        filter_bar.active_filter = self.filter_name
        filter_bar.job_count = len(self._filtered)

    def _current_record(self) -> JobRecord | None:
        table = self.query_one("#job-table", DataTable)
        row_index = table.cursor_row
        if 0 <= row_index < len(self._filtered):
            return self._filtered[row_index]
        return None

    def _update_detail(self) -> None:
        record = self._current_record()
        if record is None:
            self.query_one(DetailPane).record = None
            return
        if record.url not in self._detail_cache:
            summary = load_dashboard_record_summary(record.url)
            if summary:
                record.eval_excerpt = summary
            self._detail_cache[record.url] = record
        detail = self.query_one(DetailPane)
        detail.record = self._detail_cache.get(record.url, record)
        detail.scroll_y = 0

    def _set_status_msg(self, message: str) -> None:
        self.notify(message, timeout=2.5)

    def _focus_row_by_url(self, url: str, fallback_index: int = 0) -> None:
        table = self.query_one("#job-table", DataTable)
        if not table.row_count:
            self._update_detail()
            return
        for index, record in enumerate(self._filtered):
            if record.url == url:
                table.move_cursor(row=index)
                self._update_detail()
                return
        table.move_cursor(row=min(fallback_index, table.row_count - 1))
        self._update_detail()

    def on_data_table_row_highlighted(self, _: DataTable.RowHighlighted) -> None:
        self._update_detail()

    def _handle_header_sort(self, event: DataTable.HeaderSelected) -> None:
        clicked_key = event.column_key.value or event.label.plain.lower()
        if self._header_sort_key == clicked_key:
            self._header_sort_reverse = not self._header_sort_reverse
        else:
            self._header_sort_key = clicked_key
            self._header_sort_reverse = False
        current = self._current_record()
        current_url = current.url if current else ""
        self._apply_filter()
        self._focus_row_by_url(current_url, 0)
        direction = "desc" if self._header_sort_reverse else "asc"
        self._set_status_msg(f"Sorted by {clicked_key} {direction}")

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        self._handle_header_sort(event)

    def action_cursor_down(self) -> None:
        self.query_one("#job-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#job-table", DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one("#job-table", DataTable)
        if table.row_count:
            table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one("#job-table", DataTable)
        if table.row_count:
            table.move_cursor(row=table.row_count - 1)

    def action_prev_tab(self) -> None:
        current_index = FILTER_OPTIONS.index(self.filter_name)
        next_index = (current_index - 1) % len(FILTER_OPTIONS)
        self._set_filter(FILTER_OPTIONS[next_index])

    def action_next_tab(self) -> None:
        current_index = FILTER_OPTIONS.index(self.filter_name)
        next_index = (current_index + 1) % len(FILTER_OPTIONS)
        self._set_filter(FILTER_OPTIONS[next_index])

    def _set_filter(self, name: str) -> None:
        self.filter_name = name
        self._apply_filter()
        self._focus_row_by_url("", 0)
        self._set_status_msg(FILTER_LABELS[name])

    def action_filter_1(self) -> None: self._set_filter(FILTER_OPTIONS[0])
    def action_filter_2(self) -> None: self._set_filter(FILTER_OPTIONS[1])
    def action_filter_3(self) -> None: self._set_filter(FILTER_OPTIONS[2])
    def action_filter_4(self) -> None: self._set_filter(FILTER_OPTIONS[3])
    def action_filter_5(self) -> None: self._set_filter(FILTER_OPTIONS[4])
    def action_filter_6(self) -> None: self._set_filter(FILTER_OPTIONS[5])
    def action_filter_7(self) -> None: self._set_filter(FILTER_OPTIONS[6])
    def action_filter_8(self) -> None: self._set_filter(FILTER_OPTIONS[7])

    def _sync_record(self, record: JobRecord, new_status: str) -> None:
        if new_status == "sponsorship_fail":
            record.status = "rejected"
            record.notes = upsert_rejection_reason(record.notes, "sponsorship_fail")
        elif new_status == "seniority_fail":
            record.status = "rejected"
            record.notes = upsert_rejection_reason(record.notes, "seniority_fail")
        elif new_status == "rejected":
            record.status = "rejected"
            record.notes = upsert_rejection_reason(record.notes, "")
        else:
            record.status, _ = normalize_record_status(new_status, record.notes)
            record.notes = upsert_rejection_reason(record.notes, "")

    def _set_status(self, status: str) -> None:
        record = self._current_record()
        if record is None:
            self._set_status_msg("No row selected")
            return
        row_index = self.query_one("#job-table", DataTable).cursor_row
        next_url = ""
        if row_index + 1 < len(self._filtered):
            next_url = self._filtered[row_index + 1].url
        if not update_tracker_status(record.url, status):
            self._set_status_msg("Status update failed")
            return

        self._sync_record(record, status)
        self._detail_cache.pop(record.url, None)
        self._apply_filter()
        focus_url = record.url if record in self._filtered else next_url
        self._focus_row_by_url(focus_url, row_index)
        self._set_status_msg(f"{record.company} -> {format_status(record)}")

    def _run_optional_artifact(self, script_name: str, label: str) -> None:
        record = self._current_record()
        if record is None:
            self._set_status_msg("No row selected")
            return

        if not self._model_override:
            self.push_screen(
                ModelPromptScreen(),
                callback=lambda selected: self._after_model_prompt(selected, script_name, label),
            )
            return

        self._run_optional_artifact_with_model(script_name, label)

    def _after_model_prompt(self, selected: str | None, script_name: str, label: str) -> None:
        if not selected:
            self._set_status_msg("Model selection cancelled")
            return
        self._model_override = selected.strip()
        os.environ["MODEL_OVERRIDE"] = self._model_override
        self._set_status_msg(f"Model set to {self._model_override}")
        self._run_optional_artifact_with_model(script_name, label)

    def _run_optional_artifact_with_model(self, script_name: str, label: str) -> None:
        record = self._current_record()
        if record is None:
            self._set_status_msg("No row selected")
            return

        self._set_status_msg(f"Running {label} for {record.company}")
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / script_name), record.url],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "MODEL_OVERRIDE": self._model_override},
        )

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            self._set_status_msg(f"{label} failed{suffix}")
            return

        refreshed = load_dashboard_record_detail(record.url)
        if refreshed is not None:
            self._detail_cache[record.url] = refreshed
        else:
            self._detail_cache.pop(record.url, None)
        self._update_detail()
        self._set_status_msg(f"{label} generated for {record.company}")

    def action_status_applied(self) -> None: self._set_status("applied")
    def action_status_skipped(self) -> None: self._set_status("skipped")
    def action_status_callback(self) -> None: self._set_status("callback")
    def action_status_interview(self) -> None: self._set_status("interview")
    def action_status_rejected(self) -> None: self._set_status("rejected")
    def action_status_sponsor_fail(self) -> None: self._set_status("sponsorship_fail")
    def action_status_seniority_fail(self) -> None: self._set_status("seniority_fail")
    def action_generate_oferta(self) -> None: self._run_optional_artifact("oferta.py", "Oferta")
    def action_generate_outreach(self) -> None: self._run_optional_artifact("contacto.py", "Outreach")

    def action_reload(self) -> None:
        current = self._current_record()
        current_url = current.url if current else ""
        self._detail_cache.clear()
        self._load_data()
        self._focus_row_by_url(current_url, 0)
        self._set_status_msg(f"Reloaded {len(self._filtered)} rows")

    def action_options(self) -> None:
        self.push_screen(HelpScreen())

    def action_search(self) -> None:
        search = self.query_one("#search-bar", Input)
        search.add_class("visible")
        search.value = self.search_query
        search.focus()
        self._search_active = True

    @on(Input.Changed, "#search-bar")
    def on_search_changed(self, event: Input.Changed) -> None:
        self.search_query = event.value
        current = self._current_record()
        current_url = current.url if current else ""
        self._apply_filter()
        self._focus_row_by_url(current_url, 0)

    @on(Input.Submitted, "#search-bar")
    def on_search_submitted(self, _: Input.Submitted) -> None:
        self._close_search()

    def _close_search(self) -> None:
        search = self.query_one("#search-bar", Input)
        search.remove_class("visible")
        self._search_active = False
        self.query_one("#job-table", DataTable).focus()

    def on_key(self, event) -> None:
        if event.key == "escape" and self._search_active:
            self.search_query = ""
            self._apply_filter()
            self._close_search()
            event.prevent_default()
            event.stop()

    def action_quit(self) -> None:
        selected_index = self.query_one("#job-table", DataTable).cursor_row
        save_dashboard_session(self.filter_name, selected_index)
        self.exit()


def main() -> None:
    parser = argparse.ArgumentParser(description="ds-radar interactive dashboard")
    parser.add_argument("--sort", default="date", choices=["date", "grade", "company", "score"])
    parser.add_argument("--filter", default="all", choices=list(FILTER_OPTIONS))
    parser.add_argument("--model", default=None, help="Model override for optional dashboard actions")
    parser.add_argument("--dump-row", type=int, default=None, metavar="INDEX")
    args = parser.parse_args()

    if args.model:
        os.environ["MODEL_OVERRIDE"] = args.model

    session = load_dashboard_session()
    session_filter = session.get("filter_name", "all")
    if session_filter not in FILTER_OPTIONS:
        session_filter = "all"
    filter_name = args.filter if args.filter != "all" else session_filter

    if args.dump_row is not None:
        records = load_dashboard_records(sort_by=args.sort)
        filtered = filter_records(records, filter_name)
        if not filtered:
            print("No rows available for current filter.")
            return
        index = max(0, min(args.dump_row, len(filtered) - 1))
        print(filtered[index].to_json())
        return

    DashboardApp(
        sort_by=args.sort,
        filter_name=filter_name,
        initial_index=session.get("selected_index", 0),
    ).run()


if __name__ == "__main__":
    main()
