"""
ds-radar interactive review cockpit
Usage: python scripts/dashboard.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.containers import ConditionalContainer, Float, FloatContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame

try:
    from job_data import (
        FILTER_OPTIONS,
        JobRecord,
        filter_records,
        get_apply_preflight,
        load_job_records,
        update_tracker_status,
    )
except ImportError:  # pragma: no cover - module execution fallback
    from scripts.job_data import (
        FILTER_OPTIONS,
        JobRecord,
        filter_records,
        get_apply_preflight,
        load_job_records,
        update_tracker_status,
    )

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
    "x": "skipped",
    "K": "skipped",
}
REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_STATE_FILE = REPO_ROOT / ".dashboard.state.json"
FOCUS_ORDER = ["jobs", "evaluation", "details"]
KEY_HINTS = (
    "1-5 filter  j/k move  h/l pane  / search  e eval  c cv  o outreach  "
    "p apply  m mock  u/v/a/x status  r reload  ? help  q quit"
)


class Pet:
    """Cheerleader companion — walks, cheers, reacts to grades, and throws messages."""

    TICK_INTERVAL = 0.28
    MOOD_HOLD_SECONDS = 5.0
    MESSAGE_ROTATE_SECONDS = 5.5

    MESSAGES: dict[str, list[str]] = {
        "idle":      [
            "Find your dream role! ",
            "Keep exploring!       ",
            "You've got this!      ",
            "The right job is out there",
            "Stay curious!         ",
            "Dream job incoming... ",
            "Scanning the market...",
            "Every rejection = data",
        ],
        "excited":   [
            "APPLY NOW! This is it!",
            "Top-tier match! Go!!!  ",
            "A-grade alert! Don't miss this!",
            "Perfect fit detected! ",
            "This one has your name on it",
        ],
        "happy":     [
            "Solid pick! Worth a shot",
            "Good fit — send it!   ",
            "This could be the one!",
            "Nice role! Go for it! ",
            "B+ vibes. Apply!      ",
        ],
        "concerned": [
            "Keep looking...       ",
            "Not quite your match  ",
            "Better ones ahead!    ",
            "Onto the next one     ",
            "This market has more  ",
        ],
        "applied":   [
            "Go get 'em! \\o/      ",
            "Fingers crossed!!!    ",
            "Best of luck out there",
            "Rooting for you!      ",
            "You've totally got this",
        ],
        "cv_ready":  [
            "Resume looks sharp!   ",
            "CV polished and ready!",
            "Almost there!         ",
            "Ready to roll!        ",
        ],
    }

    def __init__(self) -> None:
        self.x = 0
        self.direction = 1
        self.mood = "idle"
        self.frame = 0
        self.last_tick = 0.0
        self.last_width = 0
        self.action = "walk"
        self.mood_until = 0.0
        self._msg_idx = 0
        self._last_msg_tick = 0.0
        self._current_msg = self.MESSAGES["idle"][0]

    def on_event(self, event: str) -> None:
        now = time.monotonic()
        if event == "applied":
            self.mood = "applied"
            self.action = "celebrate"
            self.mood_until = now + self.MOOD_HOLD_SECONDS
            self._pick_message("applied")
        elif event == "cv_ready":
            self.mood = "cv_ready"
            self.action = "celebrate"
            self.mood_until = now + self.MOOD_HOLD_SECONDS
            self._pick_message("cv_ready")
        elif event == "good_grade_a":
            self.mood = "excited"
            self.action = "celebrate"
            self.mood_until = now + self.MOOD_HOLD_SECONDS
            self._pick_message("excited")
        elif event == "good_grade":
            self.mood = "happy"
            self.action = "celebrate"
            self.mood_until = now + self.MOOD_HOLD_SECONDS
            self._pick_message("happy")
        elif event == "bad_grade":
            self.mood = "concerned"
            self.action = "sit"
            self.mood_until = now + self.MOOD_HOLD_SECONDS
            self._pick_message("concerned")
        else:
            self.mood = "idle"
            self.action = "walk"
            self.mood_until = 0.0

    def _pick_message(self, mood_key: str) -> None:
        msgs = self.MESSAGES.get(mood_key, self.MESSAGES["idle"])
        self._msg_idx = random.randrange(len(msgs))
        self._current_msg = msgs[self._msg_idx]
        self._last_msg_tick = time.monotonic()

    def get_message(self) -> str:
        now = time.monotonic()
        mood_key = self.mood if self.mood in self.MESSAGES else "idle"
        msgs = self.MESSAGES[mood_key]
        if now - self._last_msg_tick >= self.MESSAGE_ROTATE_SECONDS:
            self._msg_idx = (self._msg_idx + 1) % len(msgs)
            self._current_msg = msgs[self._msg_idx]
            self._last_msg_tick = now
        return self._current_msg

    def tick(self, width: int) -> None:
        try:
            now = time.monotonic()
            if width <= 8:
                self.last_width = width
                return
            if self.last_width and self.last_width != width:
                self.x = min(self.x, max(0, width - self.sprite_width()))
            self.last_width = width
            if now - self.last_tick < self.TICK_INTERVAL:
                return
            self.last_tick = now
            self.frame = (self.frame + 1) % 4

            if self.mood_until and now >= self.mood_until:
                self.mood = "idle"
                self.action = "walk"
                self.mood_until = 0.0

            if self.action == "walk":
                self.x += self.direction
            elif self.action == "sit":
                if self.frame % 2 == 0:
                    self.action = "walk"
            elif self.action == "celebrate":
                self.x += self.direction
                if self.frame % 3 == 2:
                    self.action = "walk"

            limit = max(0, width - self.sprite_width())
            if self.x <= 0:
                self.x = 0
                self.direction = 1
            elif self.x >= limit:
                self.x = limit
                self.direction = -1

            if self.mood == "idle" and random.random() < 0.08:
                self.action = random.choice(["look", "sit", "walk", "walk"])
        except Exception:
            self.mood = "idle"
            self.action = "walk"

    def sprite_width(self) -> int:
        return 7

    def _sprite(self) -> tuple[str, str, str]:
        right = self.direction >= 0
        f = self.frame

        if self.mood in ("excited", "applied"):
            # Jump with arms raised high
            body = r" \O/   " if f % 2 == 0 else r" /O\   "
            return (body, r"  ||   ", r"  ^^   ")

        if self.mood in ("happy", "cv_ready") or self.action == "celebrate":
            # Cheering — alternating pom-pom arms
            if f % 2 == 0:
                return (r" \o/   ", r"  |    ", r" / \   ")
            return (r" /o\   ", r"  |    ", r" / \   ")

        if self.mood == "concerned":
            face = r" (-.-)  " if f % 2 == 0 else r" (-_-)  "
            return (r"  __   ", face[:7], r" /~~\  ")

        if self.action == "sit":
            face = r" (uu)  " if f % 2 == 0 else r" (u_u) "
            return (r"  __   ", face, r"  ~~   ")

        if self.action == "look":
            eyes = "o o" if f % 2 == 0 else "o O"
            return (r"  __   ", f" ({eyes}) ", r" /__\  ")

        # Walk
        if right:
            feet = r" _/ \  " if f % 2 == 0 else r" / \_  "
            return (r"  __   ", r" (o>)  ", feet)
        feet = r"  / \_ " if f % 2 == 0 else r" _/ \  "
        return (r"  __   ", r" (<o)  ", feet)

    def _place(self, width: int, text: str) -> str:
        if width <= 0:
            return ""
        x = max(0, min(self.x, max(0, width - len(text))))
        line = [" "] * width
        for idx, char in enumerate(text[:width]):
            target = x + idx
            if target >= width:
                break
            line[target] = char
        return "".join(line).rstrip() or " "

    def _bubble(self, width: int) -> str:
        """Speech bubble centred above the pet, or nudged toward centre if pet is near edge."""
        msg = self.get_message().strip()
        bubble = f'"{msg}"'
        bw = len(bubble)
        if width <= bw + 2:
            return bubble[:width]
        # Centre the bubble
        bx = max(0, (width - bw) // 2)
        line = [" "] * width
        for i, ch in enumerate(bubble):
            if bx + i < width:
                line[bx + i] = ch
        return "".join(line).rstrip() or " "

    def render(self, width: int) -> list[tuple[str, str]]:
        try:
            self.tick(width)
            if width < 16:
                return []
            top, mid, low = self._sprite()
            body_style = (
                "class:pet_excited" if self.mood in ("excited", "applied")
                else "class:pet_happy" if self.mood in ("happy", "cv_ready")
                else "class:pet_warn" if self.mood == "concerned"
                else "class:pet"
            )
            msg_style = (
                "class:pet_excited" if self.mood in ("excited", "applied")
                else "class:pet_happy" if self.mood in ("happy", "cv_ready")
                else "class:pet_warn" if self.mood == "concerned"
                else "class:pet_msg"
            )
            floor = "─" * max(0, width - 1)
            lines = [
                (msg_style,        self._bubble(width)),
                (body_style,       self._place(width, top)),
                (body_style,       self._place(width, mid)),
                ("class:pet_floor", floor),
            ]
            fragments: list[tuple[str, str]] = []
            for idx, (line_style, line) in enumerate(lines):
                fragments.append((line_style, line))
                if idx < len(lines) - 1:
                    fragments.append(("", "\n"))
            return fragments
        except Exception:
            return []


@dataclass
class DashboardState:
    sort_by: str = "date"
    filter_name: str = "all"
    selected_index: int = 0
    message: str = ""
    apply_dry_run: bool = True
    pending_apply_url: str = ""
    apply_preflight: dict | None = None
    focus_pane: str = "jobs"
    help_visible: bool = False
    eval_scroll: int = 0
    detail_scroll: int = 0
    show_mock: bool = False
    search_query: str = ""
    search_active: bool = False
    pet: Pet = field(default_factory=Pet)

    def __post_init__(self) -> None:
        self.records = load_job_records(sort_by=self.sort_by)
        self._clamp_index()
        self.sync_pet_to_current_record()

    @property
    def filtered_records(self) -> list[JobRecord]:
        rows = filter_records(self.records, self.filter_name)
        if not self.show_mock:
            rows = [record for record in rows if (record.jd_src or "").upper() == "REAL"]
        if self.search_query:
            q = self.search_query.lower()
            rows = [
                r for r in rows
                if q in r.company.lower() or q in r.role.lower() or q in (r.status or "").lower()
            ]
        return rows

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
        self.sync_pet_to_current_record()

    def switch_focus(self, delta: int) -> None:
        index = FOCUS_ORDER.index(self.focus_pane)
        index = max(0, min(index + delta, len(FOCUS_ORDER) - 1))
        self.focus_pane = FOCUS_ORDER[index]
        self.message = f"Focus: {self.focus_pane.title()}"

    def scroll_active_pane(self, delta: int) -> None:
        if self.focus_pane == "jobs":
            self.move(delta)
            return
        if self.focus_pane == "evaluation":
            self.eval_scroll = max(0, self.eval_scroll + delta)
            return
        self.detail_scroll = max(0, self.detail_scroll + delta)

    def set_filter(self, filter_name: str) -> None:
        self.filter_name = filter_name
        self.selected_index = 0
        self._clamp_index()
        self.eval_scroll = 0
        self.detail_scroll = 0
        self.sync_pet_to_current_record()
        self.message = f"Filter: {FILTER_LABELS[filter_name]}"

    def toggle_mock(self) -> None:
        self.show_mock = not self.show_mock
        self.selected_index = 0
        self._clamp_index()
        self.eval_scroll = 0
        self.detail_scroll = 0
        self.sync_pet_to_current_record()
        if self.show_mock:
            self.message = "Filter: REAL + MOCK"
        else:
            self.message = "Filter: REAL only"

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
        self.sync_pet_to_current_record()
        self.message = "Reloaded tracker and filesystem artifacts."

    def set_status(self, status: str) -> None:
        record = self.current_record()
        if record is None:
            self.message = "No row selected."
            return
        if update_tracker_status(record.url, status):
            self.reload()
            if status in {"cv_ready", "applied"}:
                self.pet.on_event(status)
            self.message = f"Status updated: {record.company} -> {status}"
        else:
            self.message = f"Status update failed for {record.company}."

    def request_apply(self) -> None:
        record = self.current_record()
        if record is None:
            self.message = "No row selected."
            return
        preflight = get_apply_preflight(record.url)
        if preflight is None:
            self.clear_apply_request()
            self.message = "Apply aborted: could not load preflight data for selected row."
            return

        self.apply_preflight = preflight
        mode = "DRY-RUN" if self.apply_dry_run else "LIVE"
        cv_path = preflight.get("cv_path", "")
        candidates = preflight.get("cv_candidates", [])
        if preflight.get("ambiguous_cv"):
            self.clear_apply_request()
            shown = ", ".join(candidates[:3]) if candidates else "none"
            self.message = f"No unambiguous CV for this job; fix artifacts or tracker before applying. Candidates: {shown}"
            return
        if not cv_path:
            self.clear_apply_request()
            self.message = "Apply aborted: no PDF CV resolved for this job."
            return

        self.pending_apply_url = record.url
        self.message = f"Preflight OK [{mode}] {record.company} | CV={cv_path}. Confirm apply? [y/N]"

    def clear_apply_request(self) -> None:
        self.pending_apply_url = ""
        self.apply_preflight = None

    def toggle_help(self) -> None:
        self.help_visible = not self.help_visible
        if self.help_visible:
            self.message = "Help overlay open. Press ? or Esc to close."
        else:
            self.message = "Help overlay closed."

    def sync_pet_to_current_record(self) -> None:
        record = self.current_record()
        if record is None:
            self.pet.on_event("reset")
            return
        if record.grade == "A":
            self.pet.on_event("good_grade_a")
        elif record.grade == "B":
            self.pet.on_event("good_grade")
        elif record.grade in {"D", "F"}:
            self.pet.on_event("bad_grade")
        else:
            self.pet.on_event("reset")


def build_apply_command(url: str, dry_run: bool, cv_path: str = "", job_key: str = "") -> list[str]:
    command = [sys.executable, "scripts/apply.py"]
    if dry_run:
        command.append("--dry-run")
    if cv_path:
        command.extend(["--cv-path", cv_path])
    if job_key:
        command.extend(["--job-key", job_key])
    command.append(url)
    return command


def run_apply_command(url: str, dry_run: bool, cv_path: str = "", job_key: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_apply_command(url, dry_run, cv_path=cv_path, job_key=job_key),
        cwd=REPO_ROOT,
        text=True,
        check=False,
    )


def startup_log(state: DashboardState) -> str:
    counts = {
        name: len([record for record in filter_records(state.records, name) if state.show_mock or (record.jd_src or "").upper() == "REAL"])
        for name in FILTER_OPTIONS
    }
    return (
        "[dashboard] loaded tracker review cockpit\n"
        f"[dashboard] rows={len(state.filtered_records)} sort={state.sort_by} mock={'on' if state.show_mock else 'off'} "
        f"filters=all:{counts['all']} b_plus:{counts['b_plus']} "
        f"sponsorship_fail:{counts['sponsorship_fail']} linkedin:{counts['linkedin_only']} "
        f"ready:{counts['ready']}"
    )


def format_path(path_text: str) -> str:
    return path_text if path_text else "—"


def pane_title(state: DashboardState, pane: str, label: str) -> tuple[str, str]:
    style = "class:pane_active" if state.focus_pane == pane else "class:pane_inactive"
    marker = "▸" if state.focus_pane == pane else " "
    return style, f"{marker} {label}"


def _slice_lines(lines: list[tuple[str, str]], offset: int) -> list[tuple[str, str]]:
    chunks = []
    for style, text in lines:
        pieces = text.splitlines() or [text]
        for piece in pieces:
            chunks.append((style, piece))
    visible = chunks[offset:]
    if not visible:
        return [("class:muted", "No additional content.")]
    output: list[tuple[str, str]] = []
    for idx, (style, line) in enumerate(visible):
        output.append((style, line))
        if idx < len(visible) - 1:
            output.append(("", "\n"))
    return output


_GRADE_STYLE = {"A": "class:grade_a", "B": "class:grade_b", "C": "class:grade_c",
                "D": "class:grade_d", "F": "class:grade_f"}


def render_table(state: DashboardState) -> list[tuple[str, str]]:
    rows = state.filtered_records
    total_all = len(filter_records(state.records, state.filter_name))
    visible_label = f"{len(rows)} shown" if len(rows) != total_all else f"{len(rows)} jobs"
    fragments: list[tuple[str, str]] = [pane_title(state, "jobs", f"Jobs  {visible_label}"), ("", "\n")]
    header = f"{'DATE':<10} {'G':<2} {'SCR':<5} {'SP':<4} {'STATUS':<8} {'COMPANY':<16} ROLE"
    fragments.append(("class:header", header))
    fragments.append(("", "\n"))

    if not rows:
        fragments.append(("class:muted", "  No rows match the current filter."))
        return fragments

    start = max(0, state.selected_index - (VISIBLE_ROWS // 2))
    end = min(len(rows), start + VISIBLE_ROWS)
    start = max(0, end - VISIBLE_ROWS)

    for index in range(start, end):
        record = rows[index]
        is_sel = index == state.selected_index
        row_style = "class:selected" if is_sel else ""
        grade_style = row_style or _GRADE_STYLE.get(record.grade, "")
        prefix = ">" if is_sel else " "
        score_str = record.score if record.score and record.score != "?" else "  -  "
        status_short = (record.status or "")[:7]
        fragments.extend([
            (row_style,    f"{prefix} {record.date:<10} "),
            (grade_style,  f"{record.grade:<2}"),
            (row_style,    f" {score_str:<5} {record.spons:<4} {status_short:<8} "
                           f"{record.company[:16]:<16} {record.role[:30]}"),
            ("",           "\n"),
        ])

    fragments.append((
        "class:muted",
        f"  {start + 1}–{end} of {len(rows)}  ·  row {state.selected_index + 1}",
    ))
    return fragments


def render_evaluation(state: DashboardState) -> list[tuple[str, str]]:
    record = state.current_record()
    if record is None:
        return [("class:muted", "No record selected.")]

    grade_style = f"class:grade_{record.grade.lower()}"
    lines = [
        pane_title(state, "evaluation", "Evaluation"),
        ("", "\n"),
        (grade_style, f"Grade {record.grade}"),
        ("class:score", f"  Score {record.score}\n"),
        ("", f"Status: {record.status}\n"),
        ("", f"Source: {record.source}\n"),
        ("", f"JD Source: {record.jd_src}\n"),
        ("", f"Sponsorship: {record.spons}\n"),
        ("", f"Ready to apply: {'yes' if record.ready_to_apply else 'no'}\n\n"),
        ("class:label", "Paths\n"),
        ("", f"Eval: {format_path(record.eval_path)}\n"),
        ("", f"CV: {format_path(record.cv_path)}\n"),
        ("", f"Oferta: {format_path(record.oferta_path)}\n"),
        ("", f"Outreach: {format_path(record.outreach_path)}\n\n"),
        ("class:label", "URLs\n"),
        ("", f"{record.url}\n"),
    ]

    if state.apply_preflight and state.pending_apply_url == record.url:
        mode = "DRY-RUN" if state.apply_dry_run else "LIVE"
        candidates = state.apply_preflight.get("cv_candidates", [])
        lines.extend(
            [
                ("class:label", "Apply Preflight\n"),
                ("", f"Mode: {mode}\n"),
                ("", f"Job key: {state.apply_preflight.get('job_key') or '—'}\n"),
                ("", f"Chosen CV: {state.apply_preflight.get('cv_path') or '—'}\n"),
                ("", f"Candidates: {', '.join(candidates) if candidates else '—'}\n"),
            ]
        )
    return _slice_lines(lines, state.eval_scroll)


def render_details(state: DashboardState) -> list[tuple[str, str]]:
    record = state.current_record()
    if record is None:
        return [("class:muted", "No record selected.")]

    lines = [
        pane_title(state, "details", "Details"),
        ("", "\n"),
        ("class:label", "Excerpt\n"),
        ("", f"{record.eval_excerpt or 'No summary excerpt available.'}\n\n"),
        ("class:label", "Notes\n"),
        ("", f"Tracker notes: {record.notes or '—'}\n"),
        ("", f"Grade source: {record.jd_src} | Company: {record.company}\n\n"),
    ]

    lines.extend(
        [
        ("class:label", "Actions\n"),
        ("", "e eval | c cv | o outreach | p apply | r reload\n"),
        ("", "u evaluated | v cv_ready | a applied | x skipped\n"),
        ("", "j/k move | h/l switch pane | m toggle MOCK | y/n confirm | ? help | q quit\n"),
    ])
    return _slice_lines(lines, state.detail_scroll)


def render_header(state: DashboardState) -> list[tuple[str, str]]:
    total = len(state.filtered_records)
    parts: list[tuple[str, str]] = [("class:title", f"ds-radar  ({total})  ")]
    for name in FILTER_OPTIONS:
        style = "class:filter_active" if state.filter_name == name else "class:filter"
        parts.append((style, FILTER_LABELS[name]))
        parts.append(("", "  "))
    mock_style = "class:filter_active" if state.show_mock else "class:filter"
    mock_label = "M REAL+MOCK" if state.show_mock else "M REAL only"
    parts.append((mock_style, mock_label))
    if state.search_query and not state.search_active:
        parts.append(("", "  "))
        parts.append(("class:filter_active", f'/{state.search_query}'))
    return parts


def render_footer(state: DashboardState) -> list[tuple[str, str]]:
    return [("class:footer", state.message or "Ready.")]


def render_key_hints(state: DashboardState) -> list[tuple[str, str]]:
    return [("class:keybar", KEY_HINTS)]


def render_pet(state: DashboardState) -> list[tuple[str, str]]:
    width = max(0, shutil.get_terminal_size((100, 30)).columns)
    return state.pet.render(width)


def render_help() -> list[tuple[str, str]]:
    lines = [
        ("class:title", "Cockpit Help\n"),
        ("", "Navigation\n"),
        ("", "  j / down     move down in the Jobs list\n"),
        ("", "  k / up       move up in the Jobs list\n"),
        ("", "  h / left     focus Jobs ← Evaluation ← Details\n"),
        ("", "  l / right    focus Jobs → Evaluation → Details\n"),
        ("", "  m            toggle REAL-only vs REAL+MOCK\n"),
        ("", "  pageup/down  jump Jobs, or scroll Evaluation/Details\n"),
        ("", "  home / end   jump to first/last row\n\n"),
        ("", "Actions\n"),
        ("", "  e open eval   c open cv   o open outreach   p apply\n"),
        ("", "  u evaluated   v cv_ready  a applied         x skipped\n"),
        ("", "  1-5 filters   m toggle MOCK   r reload      q quit   ? close help\n"),
    ]
    return lines


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


def load_dashboard_session() -> dict:
    """Return saved session state or defaults."""
    if DASHBOARD_STATE_FILE.exists():
        try:
            return json.loads(DASHBOARD_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"filter_name": "all", "selected_index": 0}


def save_dashboard_session(state: DashboardState) -> None:
    """Persist filter and scroll position for next session."""
    DASHBOARD_STATE_FILE.write_text(
        json.dumps({"filter_name": state.filter_name, "selected_index": state.selected_index}, indent=2),
        encoding="utf-8",
    )


def build_dashboard_app(state: DashboardState) -> Application:
    def render_search_bar() -> list[tuple[str, str]]:
        if state.search_active:
            return [("class:label", f"  Search: {state.search_query}█")]
        if state.search_query:
            return [("class:muted", f"  Filter: {state.search_query}  (/ edit · Esc clear)")]
        return [("", "")]

    header_control = FormattedTextControl(lambda: render_header(state))
    search_control = FormattedTextControl(render_search_bar)
    table_control = FormattedTextControl(lambda: render_table(state), focusable=False)
    evaluation_control = FormattedTextControl(lambda: render_evaluation(state), focusable=False)
    detail_control = FormattedTextControl(lambda: render_details(state), focusable=False)
    keybar_control = FormattedTextControl(lambda: render_key_hints(state))
    footer_control = FormattedTextControl(lambda: render_footer(state))
    pet_control = FormattedTextControl(lambda: render_pet(state))
    help_control = FormattedTextControl(lambda: render_help())

    bindings = KeyBindings()

    @bindings.add("q")
    def _quit(event) -> None:
        if state.search_active:
            state.search_query += "q"
            event.app.invalidate()
            return
        event.app.exit()

    @bindings.add("up")
    def _up(event) -> None:
        state.move(-1)
        event.app.invalidate()

    @bindings.add("down")
    def _down(event) -> None:
        state.move(1)
        event.app.invalidate()

    @bindings.add("j")
    def _vim_down(event) -> None:
        state.move(1)
        event.app.invalidate()

    @bindings.add("k")
    def _vim_up(event) -> None:
        state.move(-1)
        event.app.invalidate()

    @bindings.add("h")
    @bindings.add("left")
    def _focus_left(event) -> None:
        if state.help_visible:
            return
        state.switch_focus(-1)
        event.app.invalidate()

    @bindings.add("l")
    @bindings.add("right")
    def _focus_right(event) -> None:
        if state.help_visible:
            return
        state.switch_focus(1)
        event.app.invalidate()

    @bindings.add("pageup")
    def _page_up(event) -> None:
        state.scroll_active_pane(-VISIBLE_ROWS)
        event.app.invalidate()

    @bindings.add("pagedown")
    def _page_down(event) -> None:
        state.scroll_active_pane(VISIBLE_ROWS)
        event.app.invalidate()

    @bindings.add("home")
    def _home(event) -> None:
        state.selected_index = 0
        state.sync_pet_to_current_record()
        event.app.invalidate()

    @bindings.add("end")
    def _end(event) -> None:
        if state.focus_pane == "jobs":
            state.selected_index = len(state.filtered_records) - 1
            state._clamp_index()
            state.sync_pet_to_current_record()
        event.app.invalidate()

    @bindings.add("?")
    def _toggle_help(event) -> None:
        state.toggle_help()
        event.app.invalidate()

    @bindings.add("escape")
    def _close_help(event) -> None:
        if state.search_active or state.search_query:
            state.search_active = False
            state.search_query = ""
            state.selected_index = 0
            state._clamp_index()
            state.message = "Search cleared."
            event.app.invalidate()
            return
        if state.help_visible:
            state.help_visible = False
            state.message = "Help overlay closed."
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

    @bindings.add("m")
    @bindings.add("M")
    def _toggle_mock(event) -> None:
        state.toggle_mock()
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
        preflight = state.apply_preflight
        if record is None or record.url != state.pending_apply_url or preflight is None:
            state.clear_apply_request()
            state.message = "Apply cancelled: selection changed."
            event.app.invalidate()
            return
        mode = "dry-run" if state.apply_dry_run else "live"
        state.message = f"Running apply.py ({mode}) for {record.company}..."
        event.app.invalidate()

        def _run_apply() -> None:
            result = run_apply_command(
                record.url,
                state.apply_dry_run,
                cv_path=preflight.get("cv_path", ""),
                job_key=preflight.get("job_key", ""),
            )
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

    @bindings.add("/")
    def _start_search(event) -> None:
        state.search_active = True
        state.search_query = ""
        state.selected_index = 0
        state.message = "Type to search — Enter to confirm · Esc to clear"
        event.app.invalidate()

    @bindings.add("c-h", filter=Condition(lambda: state.search_active))
    @bindings.add("backspace", filter=Condition(lambda: state.search_active))
    def _search_backspace(event) -> None:
        state.search_query = state.search_query[:-1]
        state.selected_index = 0
        state._clamp_index()
        event.app.invalidate()

    @bindings.add("enter", filter=Condition(lambda: state.search_active))
    def _search_confirm(event) -> None:
        state.search_active = False
        state.message = f"Filter: '{state.search_query}' — Esc to clear"
        event.app.invalidate()

    @bindings.add("<any>", filter=Condition(lambda: state.search_active))
    def _search_char(event) -> None:
        key = event.key_sequence[0].key
        if len(key) == 1 and key.isprintable():
            state.search_query += key
            state.selected_index = 0
            state._clamp_index()
            event.app.invalidate()

    body_container = HSplit(
        [
            Window(content=header_control, height=1),
            Window(content=search_control, height=1),
            VSplit(
                [
                    Frame(Window(content=table_control, wrap_lines=False), title="Jobs", width=Dimension(weight=5)),
                    Frame(Window(content=evaluation_control, wrap_lines=True), title="Evaluation", width=Dimension(weight=4)),
                    Frame(Window(content=detail_control, wrap_lines=True), title="Details", width=Dimension(weight=5)),
                ]
            ),
            Window(content=keybar_control, height=1),
            Window(content=footer_control, height=1),
            Window(content=pet_control, height=4),
        ]
    )

    root_container = FloatContainer(
        content=body_container,
        floats=[
            Float(
                top=2,
                left=4,
                right=4,
                bottom=4,
                content=ConditionalContainer(
                    content=Frame(Window(content=help_control, wrap_lines=True), title="Help"),
                    filter=Condition(lambda: state.help_visible),
                ),
            )
        ],
    )

    style = Style.from_dict(
        {
            "title": "bold ansicyan",
            "header": "bold ansiyellow",
            "label": "bold ansigreen",
            "muted": "#888888",
            "selected": "reverse",
            "filter": "#888888",
            "filter_active": "bold ansiblue",
            "footer": "reverse",
            "keybar": "reverse #ffffff",
            "pane_active": "bold ansiblue",
            "pane_inactive": "#888888",
            "score": "bold ansiwhite",
            "grade_a": "bold ansigreen",
            "grade_b": "bold ansicyan",
            "grade_c": "bold ansiyellow",
            "grade_d": "bold ansired",
            "grade_f": "bold ansired",
            "pet": "#aaaaaa",
            "pet_msg": "italic #aaaaaa",
            "pet_happy": "bold ansigreen",
            "pet_excited": "bold ansimagenta",
            "pet_warn": "bold ansiyellow",
            "pet_floor": "#444444",
        }
    )

    return Application(
        layout=Layout(root_container),
        key_bindings=bindings,
        full_screen=True,
        style=style,
        refresh_interval=0.2,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ds-radar interactive dashboard")
    parser.add_argument("--sort", default="date", choices=["date", "grade", "company", "score"])
    parser.add_argument("--filter", default="all", choices=FILTER_OPTIONS)
    parser.add_argument("--print-startup", action="store_true", help="Print startup log before launching")
    parser.add_argument("--dump-row", type=int, default=None, metavar="INDEX", help="Print one row model and exit")
    parser.add_argument("--apply-dry-run", action="store_true", help="Run apply.py --dry-run when pressing p (default)")
    parser.add_argument("--apply-live", action="store_true", help="Run live apply.py from the dashboard after confirmation")
    args = parser.parse_args()

    session = load_dashboard_session()
    state = DashboardState(
        sort_by=args.sort,
        filter_name=args.filter if args.filter != "all" else session.get("filter_name", "all"),
        apply_dry_run=not args.apply_live,
        selected_index=session.get("selected_index", 0),
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

    mode = "DRY-RUN" if state.apply_dry_run else "LIVE"
    state.message = (
        f"Keys: 1-5 filters | j/k or arrows move | h/l switch pane | "
        f"pageup/down scroll panes | m toggle MOCK | p apply ({mode}) | u/v/a/x set status | q quit"
    )
    app = build_dashboard_app(state)
    try:
        app.run()
    finally:
        save_dashboard_session(state)


if __name__ == "__main__":
    main()
