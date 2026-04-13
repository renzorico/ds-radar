"""
ds-radar interactive review cockpit (Textual TUI)
Usage: python scripts/dashboard.py
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Static,
)

try:
    from job_data import (
        FILTER_OPTIONS,
        JobRecord,
        filter_records,
        get_apply_preflight,
        load_job_records,
        update_tracker_status,
    )
except ImportError:
    from scripts.job_data import (
        FILTER_OPTIONS,
        JobRecord,
        filter_records,
        get_apply_preflight,
        load_job_records,
        update_tracker_status,
    )

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_STATE_FILE = REPO_ROOT / ".dashboard.state.json"

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
GRADE_STYLES = {
    "A": "bold green",
    "B": "bold cyan",
    "C": "bold yellow",
    "D": "bold red",
    "F": "bold red",
}
STATUS_STYLES = {
    "applied": "bold cyan",
    "interview": "bold green",
    "callback": "bold magenta",
    "rejected": "dim red",
    "skipped": "dim",
    "sponsorship_fail": "dim red",
}
FILTER_LABELS = {
    "all": "All",
    "linkedin": "LinkedIn",
    "boards": "Boards",
    "b_plus": "B+",
    "ready": "Ready",
    "applied": "Applied",
    "interview": "Interview",
    "callback": "Callback",
    "rejected": "Rejected",
    "sponsorship_fail": "Sponsor",
}
STATUS_ACTIONS = {
    "a": ("applied", True),
    "x": ("skipped", True),
    "i": ("interview", True),
    "c": ("callback", True),
    "f": ("sponsorship_fail", True),
    "r": ("rejected", True),
}


def _format_path(path: str) -> str:
    return path if path else "---"


def open_path_in_terminal(path_text: str) -> None:
    if not path_text:
        return
    full_path = Path(path_text)
    if not full_path.is_absolute():
        full_path = REPO_ROOT / path_text
    if not full_path.exists():
        return
    editor = os.environ.get("EDITOR")
    if editor:
        command = shlex.split(editor) + [str(full_path)]
    else:
        command = ["less", str(full_path)]
    subprocess.run(command, check=False)


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


# ---------------------------------------------------------------------------
# Help screen
# ---------------------------------------------------------------------------

HELP_TEXT = """\
[bold cyan]Navigation[/]
  [bold]j / k[/]          Move down / up in job list
  [bold]g / G[/]          Jump to first / last row
  [bold]Ctrl+D / Ctrl+U[/]  Page down / up
  [bold]Tab / Shift+Tab[/]  Cycle focus between panes
  [bold]1-9, 0[/]         Switch filter tab

[bold cyan]Status Actions[/] (auto-advance to next row)
  [bold]a[/]  applied       [bold]x[/]  skipped
  [bold]i[/]  interview     [bold]c[/]  callback
  [bold]f[/]  sponsor fail  [bold]r[/]  rejected

[bold cyan]Actions[/]
  [bold]e[/]  Open eval file      [bold]v[/]  Open CV
  [bold]o[/]  Open outreach       [bold]p[/]  Apply (preflight)
  [bold]y[/]  Confirm apply       [bold]n[/]  Cancel apply
  [bold]R[/]  Reload data         [bold]M[/]  Toggle MOCK jobs
  [bold]/[/]  Search              [bold]Esc[/]  Clear search
  [bold]?[/]  This help           [bold]q[/]  Quit
"""


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 64;
        max-height: 80%;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
    }
    HelpScreen > Vertical > Static {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[bold cyan]ds-radar Cockpit Help[/]")
            yield Static(HELP_TEXT)
            yield Static("[dim]Press ? or Esc to close[/]")


# ---------------------------------------------------------------------------
# Detail pane widget
# ---------------------------------------------------------------------------

class DetailPane(Static):
    record: reactive[JobRecord | None] = reactive(None)

    DEFAULT_CSS = """
    DetailPane {
        padding: 1 2;
        height: 100%;
        overflow-y: auto;
    }
    """

    def watch_record(self, record: JobRecord | None) -> None:
        self._render_record(record)

    def _render_record(self, record: JobRecord | None) -> None:
        if record is None:
            self.update("[dim]No record selected[/]")
            return
        grade_style = GRADE_STYLES.get(record.grade, "")
        status_style = STATUS_STYLES.get(record.status, "bold")
        lines = [
            f"[bold]{record.company}[/]",
            f"[dim]{record.role}[/]",
            "",
            f"  Grade  [{grade_style}]{record.grade}[/]   Score  [bold]{record.score}[/]",
            f"  Status [{status_style}]{record.status or '---'}[/]",
            f"  Source [dim]{record.source}[/]   JD [dim]{record.jd_src}[/]   Spons [dim]{record.spons}[/]",
            "",
            "[bold cyan]Artifacts[/]",
            f"  Eval     {_format_path(record.eval_path)}",
            f"  CV       {_format_path(record.cv_path)}",
            f"  Oferta   {_format_path(record.oferta_path)}",
            f"  Outreach {_format_path(record.outreach_path)}",
            "",
            "[bold cyan]URL[/]",
            f"  {record.url}",
        ]
        if record.eval_excerpt:
            lines += ["", "[bold cyan]Summary[/]", f"  {record.eval_excerpt}"]
        if record.notes:
            lines += ["", "[bold cyan]Notes[/]", f"  {record.notes}"]
        self.update("\n".join(lines))


# ---------------------------------------------------------------------------
# Filter bar widget
# ---------------------------------------------------------------------------

class FilterBar(Static):
    active_filter: reactive[str] = reactive("all")
    job_count: reactive[int] = reactive(0)
    show_mock: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    FilterBar {
        height: 1;
        dock: top;
        padding: 0 1;
        background: $surface-darken-1;
    }
    """

    def render(self) -> Text:
        text = Text()
        for idx, name in enumerate(FILTER_OPTIONS):
            key = str(idx + 1) if idx < 9 else "0"
            label = f" {key}:{FILTER_LABELS[name]} "
            if name == self.active_filter:
                text.append(label, style="bold reverse")
            else:
                text.append(label, style="dim")
            text.append(" ")
        mock_label = " MOCK " if self.show_mock else " REAL "
        mock_style = "bold yellow" if self.show_mock else "dim green"
        text.append("  ")
        text.append(mock_label, style=mock_style)
        text.append(f"  {self.job_count} jobs", style="dim")
        return text


# ---------------------------------------------------------------------------
# Status bar widget
# ---------------------------------------------------------------------------

class StatusBar(Static):
    message: reactive[str] = reactive("")

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $surface-darken-2;
    }
    """

    def render(self) -> Text:
        if self.message:
            return Text(f" {self.message}", style="bold")
        return Text(" Ready", style="dim")


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DashboardApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #main-area {
        height: 1fr;
    }
    #job-table {
        width: 3fr;
        height: 100%;
        border: solid $accent;
    }
    #detail-pane {
        width: 2fr;
        height: 100%;
        border: solid $primary;
        overflow-y: auto;
    }
    #search-bar {
        dock: top;
        height: 1;
        display: none;
    }
    #search-bar.visible {
        display: block;
    }
    DataTable {
        height: 100%;
    }
    DataTable > .datatable--cursor {
        background: $accent;
        color: $text;
    }
    """

    TITLE = "ds-radar"
    SUB_TITLE = "job search cockpit"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("R", "reload", "Reload", key_display="R"),
        Binding("M", "toggle_mock", "Mock", key_display="M"),
        Binding("slash", "search", "Search", key_display="/"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False, key_display="G"),
        Binding("ctrl+d", "page_down", "PgDn", show=False),
        Binding("ctrl+u", "page_up", "PgUp", show=False),
        Binding("e", "open_eval", "Eval", key_display="e"),
        Binding("v", "open_cv", "CV", key_display="v"),
        Binding("o", "open_outreach", "Outreach", key_display="o"),
        Binding("p", "apply_preflight", "Apply", key_display="p"),
        Binding("y", "apply_confirm", "Confirm", show=False),
        Binding("n", "apply_cancel", "Cancel", show=False),
        Binding("a", "status_applied", show=False),
        Binding("x", "status_skipped", show=False),
        Binding("i", "status_interview", show=False),
        Binding("c", "status_callback", show=False),
        Binding("f", "status_sponsor_fail", show=False),
        Binding("r", "status_rejected", show=False),
        Binding("1", "filter_1", show=False),
        Binding("2", "filter_2", show=False),
        Binding("3", "filter_3", show=False),
        Binding("4", "filter_4", show=False),
        Binding("5", "filter_5", show=False),
        Binding("6", "filter_6", show=False),
        Binding("7", "filter_7", show=False),
        Binding("8", "filter_8", show=False),
        Binding("9", "filter_9", show=False),
        Binding("0", "filter_0", show=False),
    ]

    sort_by: reactive[str] = reactive("date")
    filter_name: reactive[str] = reactive("all")
    show_mock: reactive[bool] = reactive(False)
    search_query: reactive[str] = reactive("")
    apply_dry_run: bool = True

    def __init__(
        self,
        sort_by: str = "date",
        filter_name: str = "all",
        apply_dry_run: bool = True,
        initial_index: int = 0,
    ) -> None:
        super().__init__()
        self.sort_by = sort_by
        self.filter_name = filter_name
        self.apply_dry_run = apply_dry_run
        self._initial_index = initial_index
        self._all_records: list[JobRecord] = []
        self._filtered: list[JobRecord] = []
        self._pending_apply_url = ""
        self._apply_preflight: dict | None = None
        self._search_active = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield FilterBar(id="filter-bar")
        search = Input(placeholder="Search company/role...", id="search-bar")
        search.display = False
        yield search
        with Horizontal(id="main-area"):
            yield DataTable(id="job-table", cursor_type="row", zebra_stripes=True)
            yield DetailPane(id="detail-pane")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#job-table", DataTable)
        table.add_columns("Grade", "Score", "Status", "Company", "Role", "Src", "CV", "Ofe")
        self._load_data()
        self.query_one(FilterBar).active_filter = self.filter_name
        if self._initial_index > 0 and self._initial_index < len(self._filtered):
            table.move_cursor(row=self._initial_index)
        self._update_detail()
        table.focus()

    def _load_data(self) -> None:
        self._all_records = load_job_records(sort_by=self.sort_by)
        self._apply_filter()

    def _apply_filter(self) -> None:
        rows = filter_records(self._all_records, self.filter_name)
        if not self.show_mock:
            rows = [r for r in rows if (r.jd_src or "").upper() == "REAL"]
        if self.search_query:
            q = self.search_query.lower()
            rows = [
                r for r in rows
                if q in r.company.lower() or q in r.role.lower() or q in (r.status or "").lower()
            ]
        self._filtered = rows
        self._populate_table()

    def _populate_table(self) -> None:
        table = self.query_one("#job-table", DataTable)
        table.clear()
        for record in self._filtered:
            grade_style = GRADE_STYLES.get(record.grade, "")
            status_style = STATUS_STYLES.get(record.status, "")
            grade_text = Text(record.grade, style=grade_style)
            score_text = Text(record.score if record.score != "?" else "-", style="bold")
            status_text = Text(record.status or "---", style=status_style)
            company_text = Text(record.company)
            role_text = Text(record.role)
            src_text = Text(record.source[:3] if record.source else "?", style="dim")
            cv_icon = Text("Y" if record.cv == "yes" else "-", style="green" if record.cv == "yes" else "dim")
            ofe_icon = Text("Y" if record.ofe == "yes" else "-", style="green" if record.ofe == "yes" else "dim")
            table.add_row(
                grade_text, score_text, status_text, company_text,
                role_text, src_text, cv_icon, ofe_icon,
            )
        filter_bar = self.query_one(FilterBar)
        filter_bar.job_count = len(self._filtered)
        filter_bar.active_filter = self.filter_name
        filter_bar.show_mock = self.show_mock

    def _current_record(self) -> JobRecord | None:
        table = self.query_one("#job-table", DataTable)
        if table.row_count == 0:
            return None
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self._filtered):
            return self._filtered[row_idx]
        return None

    def _update_detail(self) -> None:
        record = self._current_record()
        detail = self.query_one(DetailPane)
        detail.record = record

    def _set_status_msg(self, msg: str) -> None:
        self.query_one(StatusBar).message = msg

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_detail()

    # -- Navigation --

    def action_cursor_down(self) -> None:
        table = self.query_one("#job-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#job-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one("#job-table", DataTable)
        if table.row_count:
            table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one("#job-table", DataTable)
        if table.row_count:
            table.move_cursor(row=table.row_count - 1)

    def action_page_down(self) -> None:
        table = self.query_one("#job-table", DataTable)
        table.action_scroll_down()

    def action_page_up(self) -> None:
        table = self.query_one("#job-table", DataTable)
        table.action_scroll_up()

    # -- Filters --

    def _set_filter(self, name: str) -> None:
        self.filter_name = name
        self._apply_filter()
        table = self.query_one("#job-table", DataTable)
        if table.row_count:
            table.move_cursor(row=0)
        self._update_detail()
        self._set_status_msg(f"Filter: {FILTER_LABELS.get(name, name)}")

    def action_filter_1(self) -> None: self._set_filter(FILTER_OPTIONS[0])
    def action_filter_2(self) -> None: self._set_filter(FILTER_OPTIONS[1])
    def action_filter_3(self) -> None: self._set_filter(FILTER_OPTIONS[2])
    def action_filter_4(self) -> None: self._set_filter(FILTER_OPTIONS[3])
    def action_filter_5(self) -> None: self._set_filter(FILTER_OPTIONS[4])
    def action_filter_6(self) -> None: self._set_filter(FILTER_OPTIONS[5])
    def action_filter_7(self) -> None: self._set_filter(FILTER_OPTIONS[6])
    def action_filter_8(self) -> None: self._set_filter(FILTER_OPTIONS[7])
    def action_filter_9(self) -> None: self._set_filter(FILTER_OPTIONS[8])
    def action_filter_0(self) -> None: self._set_filter(FILTER_OPTIONS[9])

    # -- Status --

    def _set_status(self, status: str, auto_advance: bool = True) -> None:
        record = self._current_record()
        if record is None:
            self._set_status_msg("No row selected.")
            return
        if update_tracker_status(record.url, status):
            table = self.query_one("#job-table", DataTable)
            cursor_row = table.cursor_row
            self._load_data()
            if auto_advance and cursor_row + 1 < table.row_count:
                table.move_cursor(row=cursor_row + 1)
            elif cursor_row < table.row_count:
                table.move_cursor(row=cursor_row)
            self._update_detail()
            self._set_status_msg(f"{record.company} -> {status}")
        else:
            self._set_status_msg(f"Status update failed for {record.company}")

    def action_status_applied(self) -> None: self._set_status("applied")
    def action_status_skipped(self) -> None: self._set_status("skipped")
    def action_status_interview(self) -> None: self._set_status("interview")
    def action_status_callback(self) -> None: self._set_status("callback")
    def action_status_sponsor_fail(self) -> None: self._set_status("sponsorship_fail")
    def action_status_rejected(self) -> None: self._set_status("rejected")

    # -- Actions --

    def action_reload(self) -> None:
        record = self._current_record()
        current_url = record.url if record else ""
        self._load_data()
        if current_url:
            for idx, r in enumerate(self._filtered):
                if r.url == current_url:
                    table = self.query_one("#job-table", DataTable)
                    table.move_cursor(row=idx)
                    break
        self._update_detail()
        self._set_status_msg(f"Reloaded. {len(self._filtered)} rows.")

    def action_toggle_mock(self) -> None:
        self.show_mock = not self.show_mock
        self._apply_filter()
        table = self.query_one("#job-table", DataTable)
        if table.row_count:
            table.move_cursor(row=0)
        self._update_detail()
        label = "REAL + MOCK" if self.show_mock else "REAL only"
        self._set_status_msg(f"Showing {label}")

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_search(self) -> None:
        search = self.query_one("#search-bar", Input)
        search.display = True
        search.value = self.search_query
        search.focus()
        self._search_active = True

    @on(Input.Changed, "#search-bar")
    def on_search_changed(self, event: Input.Changed) -> None:
        self.search_query = event.value
        self._apply_filter()
        self._update_detail()

    @on(Input.Submitted, "#search-bar")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self._close_search()

    def _close_search(self) -> None:
        search = self.query_one("#search-bar", Input)
        search.display = False
        self._search_active = False
        table = self.query_one("#job-table", DataTable)
        table.focus()

    def on_key(self, event) -> None:
        if event.key == "escape" and self._search_active:
            self.search_query = ""
            self._apply_filter()
            self._update_detail()
            self._close_search()
            event.prevent_default()
            event.stop()

    # -- Open artifacts --

    def action_open_eval(self) -> None:
        record = self._current_record()
        if not record or not record.eval_path:
            self._set_status_msg("No eval file for selected row.")
            return
        self._set_status_msg(f"Opening: {record.eval_path}")
        self._open_file(record.eval_path)

    def action_open_cv(self) -> None:
        record = self._current_record()
        if not record or not record.cv_path:
            self._set_status_msg("No CV for selected row.")
            return
        self._set_status_msg(f"Opening: {record.cv_path}")
        self._open_file(record.cv_path)

    def action_open_outreach(self) -> None:
        record = self._current_record()
        if not record or not record.outreach_path:
            self._set_status_msg("No outreach for selected row.")
            return
        self._set_status_msg(f"Opening: {record.outreach_path}")
        self._open_file(record.outreach_path)

    @work(thread=True)
    def _open_file(self, path: str) -> None:
        with self.app.suspend():
            open_path_in_terminal(path)

    # -- Apply workflow --

    def action_apply_preflight(self) -> None:
        record = self._current_record()
        if record is None:
            self._set_status_msg("No row selected.")
            return
        preflight = get_apply_preflight(record.url)
        if preflight is None:
            self._set_status_msg("Apply aborted: could not load preflight data.")
            return
        if preflight.get("ambiguous_cv"):
            candidates = preflight.get("cv_candidates", [])
            shown = ", ".join(candidates[:3]) if candidates else "none"
            self._set_status_msg(f"Ambiguous CV -- fix artifacts first. Candidates: {shown}")
            return
        cv_path = preflight.get("cv_path", "")
        if not cv_path:
            self._set_status_msg("Apply aborted: no PDF CV resolved.")
            return
        self._pending_apply_url = record.url
        self._apply_preflight = preflight
        mode = "DRY-RUN" if self.apply_dry_run else "LIVE"
        self._set_status_msg(
            f"Preflight OK [{mode}] {record.company} | CV={cv_path}. Press y to confirm, n to cancel."
        )

    def action_apply_confirm(self) -> None:
        if not self._pending_apply_url or not self._apply_preflight:
            return
        record = self._current_record()
        if record is None or record.url != self._pending_apply_url:
            self._clear_apply()
            self._set_status_msg("Apply cancelled: selection changed.")
            return
        self._set_status_msg(f"Running apply.py for {record.company}...")
        self._run_apply(
            record.url,
            record.company,
            self.apply_dry_run,
            self._apply_preflight.get("cv_path", ""),
            self._apply_preflight.get("job_key", ""),
        )

    @work(thread=True)
    def _run_apply(self, url: str, company: str, dry_run: bool, cv_path: str, job_key: str) -> None:
        command = [sys.executable, "scripts/apply.py"]
        if dry_run:
            command.append("--dry-run")
        if cv_path:
            command.extend(["--cv-path", cv_path])
        if job_key:
            command.extend(["--job-key", job_key])
        command.append(url)
        result = subprocess.run(command, cwd=REPO_ROOT, text=True, check=False)
        if result.returncode == 0:
            if dry_run:
                self.call_from_thread(self._set_status_msg, f"apply.py dry-run completed for {company}")
            else:
                self.call_from_thread(self._set_status, "applied")
        else:
            self.call_from_thread(
                self._set_status_msg,
                f"apply.py failed for {company} (exit {result.returncode})",
            )
        self._clear_apply()

    def action_apply_cancel(self) -> None:
        if self._pending_apply_url:
            self._clear_apply()
            self._set_status_msg("Apply cancelled.")

    def _clear_apply(self) -> None:
        self._pending_apply_url = ""
        self._apply_preflight = None

    # -- Lifecycle --

    def action_quit(self) -> None:
        table = self.query_one("#job-table", DataTable)
        save_dashboard_session(self.filter_name, table.cursor_row)
        self.exit()


def main() -> None:
    parser = argparse.ArgumentParser(description="ds-radar interactive dashboard")
    parser.add_argument("--sort", default="date", choices=["date", "grade", "company", "score"])
    parser.add_argument("--filter", default="all", choices=list(FILTER_OPTIONS))
    parser.add_argument("--apply-dry-run", action="store_true")
    parser.add_argument("--apply-live", action="store_true")
    parser.add_argument("--dump-row", type=int, default=None, metavar="INDEX")
    args = parser.parse_args()

    session = load_dashboard_session()
    filter_name = args.filter if args.filter != "all" else session.get("filter_name", "all")

    if args.dump_row is not None:
        records = load_job_records(sort_by=args.sort)
        filtered = filter_records(records, filter_name)
        filtered = [r for r in filtered if (r.jd_src or "").upper() == "REAL"]
        if not filtered:
            print("No rows available for current filter.")
            return
        index = max(0, min(args.dump_row, len(filtered) - 1))
        print(filtered[index].to_json())
        return

    app = DashboardApp(
        sort_by=args.sort,
        filter_name=filter_name,
        apply_dry_run=not args.apply_live,
        initial_index=session.get("selected_index", 0),
    )
    app.run()


if __name__ == "__main__":
    main()
