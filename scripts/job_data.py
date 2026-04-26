"""
Shared tracker/enrichment helpers for list_jobs.py and dashboard.py.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from identity import artifact_job_key, build_job_key, load_artifact_index
except ImportError:  # pragma: no cover - module execution fallback
    from scripts.identity import artifact_job_key, build_job_key, load_artifact_index

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKER = REPO_ROOT / "tracker.tsv"
SOURCE_HISTORY = REPO_ROOT / "source-history.tsv"
SCAN_HISTORY = REPO_ROOT / "scan-history.tsv"
EVALS_DIR = REPO_ROOT / "evals"
APPLICATIONS = REPO_ROOT / "applications"

TRACKER_HEADER = [
    "date",
    "company",
    "role",
    "url",
    "grade",
    "score",
    "status",
    "pdf_path",
    "notes",
]

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
FILTER_OPTIONS = [
    "all", "a_plus", "b_plus", "to_apply",
    "applied", "callback", "interview", "rejected",
]

REJECTION_NOTE_PREFIX = "reject:"


@dataclass
class JobRecord:
    date: str
    grade: str
    score: str
    source: str
    jd_src: str
    spons: str
    cv: str
    ofe: str
    con: str
    company: str
    role: str
    status: str
    url: str
    notes: str
    eval_path: str
    eval_excerpt: str
    cv_path: str
    oferta_path: str
    outreach_path: str
    ready_to_apply: bool

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def extract_rejection_reason(notes: str) -> str:
    for part in (notes or "").split("|"):
        token = part.strip().lower()
        if token.startswith(REJECTION_NOTE_PREFIX):
            return token.removeprefix(REJECTION_NOTE_PREFIX).strip()
    return ""


def upsert_rejection_reason(notes: str, reason: str) -> str:
    parts = []
    for part in (notes or "").split("|"):
        cleaned = part.strip()
        if cleaned and not cleaned.lower().startswith(REJECTION_NOTE_PREFIX):
            parts.append(cleaned)
    if reason:
        parts.append(f"{REJECTION_NOTE_PREFIX}{reason}")
    return " | ".join(parts)


def normalize_record_status(status: str, notes: str = "") -> tuple[str, str]:
    lowered = (status or "").strip().lower()
    reason = extract_rejection_reason(notes)
    if lowered in {"sponsorship_fail", "seniority_fail"}:
        return "rejected", lowered
    if lowered == "rejected":
        return "rejected", reason
    return lowered, reason


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def load_tsv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def build_index(rows: list[dict], key_col: str) -> dict[str, dict]:
    return {row[key_col].strip(): row for row in rows if row.get(key_col)}


def infer_source(url: str, source_index: dict[str, dict]) -> str:
    row = source_index.get(url.strip())
    if row:
        return row.get("source", "ats").strip() or "ats"
    return "linkedin" if "linkedin.com" in url else "ats"


def grade_passes(grade: str, filt: str | None) -> bool:
    if not filt:
        return True
    if filt.endswith("+"):
        return GRADE_ORDER.get(grade, 99) <= GRADE_ORDER.get(filt[:-1], 99)
    if filt.endswith("-"):
        return GRADE_ORDER.get(grade, 99) >= GRADE_ORDER.get(filt[:-1], 99)
    return grade == filt


def find_eval(row: dict, scan_index: dict[str, dict]) -> Path | None:
    url = row.get("url", "").strip()
    scan_row = scan_index.get(url)
    if scan_row:
        candidate = REPO_ROOT / scan_row.get("eval_path", "")
        if candidate.exists():
            return candidate

    slug = slugify(row.get("company", ""))
    date_str = row.get("date", "")
    if slug:
        if date_str:
            dated = EVALS_DIR / f"{slug}_{date_str}.md"
            if dated.exists():
                return dated
        hits = sorted(
            (path for path in EVALS_DIR.glob(f"{slug}_*.md") if not path.name.startswith("deep_")),
            reverse=True,
        )
        if hits:
            return hits[0]
    return None


def find_latest_artifact(company: str, pattern: str, directory: Path) -> Path | None:
    slug = slugify(company)
    hits = sorted(directory.glob(pattern.format(slug=slug)), reverse=True)
    return hits[0] if hits else None


def short_role_slug(role: str, words: int = 3) -> str:
    parts = [part for part in slugify(role).split("-") if part]
    return "-".join(parts[:words])


def url_job_slug(url: str) -> str:
    text = url.strip().rstrip("/").split("/")[-1]
    text = re.sub(r"[^a-zA-Z0-9-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-").lower()
    return text


def _artifact_matches_row(path: Path, company_slug: str, role_slug: str, job_slug: str) -> bool:
    stem = path.stem.lower()
    if company_slug and company_slug not in stem:
        return False
    if job_slug and job_slug in stem:
        return True
    if role_slug and role_slug in stem:
        return True
    return False


def _company_date_key(row: dict) -> tuple[str, str]:
    return slugify(row.get("company", "")), row.get("date", "").strip()


def build_eval_job_key_map(tracker_rows: list[dict], scan_rows: list[dict]) -> dict[str, str]:
    keys: dict[str, str] = {}
    row_key_by_url = {
        row.get("url", "").strip(): build_job_key(
            url=row.get("url", ""),
            company=row.get("company", ""),
            title=row.get("role", ""),
        )
        for row in tracker_rows
        if row.get("url")
    }
    for scan_row in scan_rows:
        eval_path = scan_row.get("eval_path", "").strip()
        url = scan_row.get("url", "").strip()
        if not eval_path:
            continue
        job_key = row_key_by_url.get(url) or build_job_key(url=url)
        if job_key:
            keys[eval_path] = job_key
            keys[Path(eval_path).name] = job_key
    return keys


def _candidate_matches_row(
    path: Path,
    row_job_key: str,
    company_slug: str,
    role_slug: str,
    job_slug: str,
    artifact_index: dict[str, dict],
    eval_job_keys: dict[str, str],
) -> bool:
    candidate_key = artifact_job_key(path, artifact_index, eval_job_keys)
    if row_job_key and candidate_key:
        return row_job_key == candidate_key
    return _artifact_matches_row(path, company_slug, role_slug, job_slug)


def _artifact_candidate_groups(
    row: dict,
    company: str,
    role: str,
    candidates: list[Path],
    artifact_index: dict[str, dict],
    eval_job_keys: dict[str, str],
) -> tuple[list[Path], list[Path]]:
    company_slug = slugify(company)
    role_slug = short_role_slug(role)
    job_slug = url_job_slug(row.get("url", ""))
    row_job_key = build_job_key(url=row.get("url", ""), company=company, title=role)
    exact_matches: list[Path] = []
    heuristic_matches: list[Path] = []

    for candidate in candidates:
        candidate_key = artifact_job_key(candidate, artifact_index, eval_job_keys)
        if row_job_key and candidate_key:
            if row_job_key == candidate_key:
                exact_matches.append(candidate)
            continue
        if _artifact_matches_row(candidate, company_slug, role_slug, job_slug):
            heuristic_matches.append(candidate)

    return exact_matches, heuristic_matches


def resolve_cv_path(
    row: dict,
    company: str,
    role: str,
    related_rows: list[dict],
    artifact_index: dict[str, dict],
    eval_job_keys: dict[str, str],
) -> Path | None:
    company_slug = slugify(company)
    tracker_path = row.get("pdf_path", "").strip()
    if tracker_path:
        candidate = REPO_ROOT / tracker_path
        role_slug = short_role_slug(role)
        job_slug = url_job_slug(row.get("url", ""))
        row_job_key = build_job_key(url=row.get("url", ""), company=company, title=role)
        if candidate.exists() and _candidate_matches_row(
            candidate,
            row_job_key,
            company_slug,
            role_slug,
            job_slug,
            artifact_index,
            eval_job_keys,
        ):
            return candidate

    all_candidates: list[Path] = []
    for pattern in ("cv_{slug}_*.pdf", "cv_{slug}_*.md"):
        all_candidates.extend(sorted(APPLICATIONS.glob(pattern.format(slug=company_slug)), reverse=True))

    exact_matches, heuristic_matches = _artifact_candidate_groups(
        row, company, role, all_candidates, artifact_index, eval_job_keys
    )

    if exact_matches:
        return exact_matches[0]

    unique_stems = {c.stem for c in all_candidates}
    if len(related_rows) == 1 or len(unique_stems) == 1:
        for pattern in ("cv_{slug}_*.pdf", "cv_{slug}_*.md"):
            candidate = find_latest_artifact(company, pattern, APPLICATIONS)
            if candidate:
                return candidate

    if heuristic_matches:
        return heuristic_matches[0]
    return None


def resolve_related_artifact(
    row: dict,
    company: str,
    role: str,
    related_rows: list[dict],
    directory: Path,
    pattern: str,
    artifact_index: dict[str, dict],
    eval_job_keys: dict[str, str],
) -> Path | None:
    company_slug = slugify(company)
    candidates = sorted(directory.glob(pattern.format(slug=company_slug)), reverse=True)
    exact_matches, heuristic_matches = _artifact_candidate_groups(
        row, company, role, candidates, artifact_index, eval_job_keys
    )

    if exact_matches:
        return exact_matches[0]
    if len(related_rows) == 1 or len(candidates) == 1:
        return candidates[0] if candidates else None
    if heuristic_matches:
        return heuristic_matches[0]
    return None


def get_apply_preflight(url: str) -> dict | None:
    tracker_rows = load_tsv(TRACKER)
    scan_rows = load_tsv(SCAN_HISTORY)
    artifact_index = load_artifact_index()
    eval_job_keys = build_eval_job_key_map(tracker_rows, scan_rows)
    rows_by_company_date: dict[tuple[str, str], list[dict]] = {}
    for tracker_row in tracker_rows:
        rows_by_company_date.setdefault(_company_date_key(tracker_row), []).append(tracker_row)

    row = next((item for item in tracker_rows if item.get("url", "").strip() == url.strip()), None)
    records = load_job_records(sort_by="date")
    record = next((item for item in records if item.url == url.strip()), None)
    if row is None or record is None:
        return None

    company = row.get("company", "").strip()
    role = row.get("role", "").strip()
    job_key = build_job_key(url=url, company=company, title=role)
    related_rows = rows_by_company_date.get(_company_date_key(row), [])

    tracker_candidate = row.get("pdf_path", "").strip()
    candidates: list[Path] = []
    if tracker_candidate:
        tracker_path = REPO_ROOT / tracker_candidate
        if tracker_path.exists():
            candidates.append(tracker_path)
    company_slug = slugify(company)
    for pattern in ("cv_{slug}_*.pdf", "cv_{slug}_*.md"):
        for candidate in sorted(APPLICATIONS.glob(pattern.format(slug=company_slug)), reverse=True):
            if candidate not in candidates:
                candidates.append(candidate)

    exact_matches, heuristic_matches = _artifact_candidate_groups(
        row, company, role, candidates, artifact_index, eval_job_keys
    )

    preferred_candidates = exact_matches or heuristic_matches
    upload_candidates = [path for path in preferred_candidates if path.suffix.lower() == ".pdf"]
    chosen_cv = upload_candidates[0] if len(upload_candidates) == 1 else None
    ambiguous = len(upload_candidates) > 1

    if not chosen_cv and len(related_rows) == 1 and not exact_matches and not heuristic_matches:
        fallback = find_latest_artifact(company, "cv_{slug}_*.pdf", APPLICATIONS)
        if fallback:
            chosen_cv = fallback

    return {
        "record": record,
        "job_key": job_key,
        "cv_path": str(chosen_cv.relative_to(REPO_ROOT)) if chosen_cv else "",
        "cv_candidates": [str(path.relative_to(REPO_ROOT)) for path in preferred_candidates],
        "cv_upload_candidates": [str(path.relative_to(REPO_ROOT)) for path in upload_candidates],
        "ambiguous_cv": ambiguous or len(preferred_candidates) > 1 and not upload_candidates,
        "ready": bool(chosen_cv),
    }


def read_eval_meta(eval_path: Path | None, tracker_notes: str) -> tuple[str, str]:
    jd_src = tracker_notes if tracker_notes in ("REAL", "MOCK") else "?"
    if eval_path is None:
        return jd_src, "?"

    try:
        text = eval_path.read_text(encoding="utf-8")
    except OSError:
        return jd_src, "?"

    if jd_src == "?":
        if "[JD_SOURCE: REAL]" in text:
            jd_src = "REAL"
        elif "[JD_SOURCE: MOCK]" in text:
            jd_src = "MOCK"

    spons = "PASS"
    for line in text.splitlines()[:6]:
        if "SPONSORSHIP GATE FAIL" in line:
            spons = "FAIL"
            break
    else:
        match = re.search(r"## Sponsorship\n\*\*Status:\*\* (NEGATIVE|POSITIVE|NEUTRAL)", text)
        if match:
            spons = "FAIL" if match.group(1) == "NEGATIVE" else "PASS"

    return jd_src, spons


def extract_markdown_section(path: Path | None, headings: list[str]) -> str:
    if path is None or not path.exists():
        return ""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    for heading in headings:
        pattern = rf"{re.escape(heading)}\s*\n([\s\S]+?)(?=\n##|\Z)"
        match = re.search(pattern, text)
        if match:
            return normalize_excerpt(match.group(1))

    return normalize_excerpt(text[:500])


def normalize_excerpt(text: str, limit: int = 360) -> str:
    cleaned = re.sub(r"\s+", " ", text)
    cleaned = re.sub(r"^[#*\-\d.\s]+", "", cleaned).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def sort_records(records: list[JobRecord], sort_by: str) -> list[JobRecord]:
    def sort_key(record: JobRecord):
        if sort_by == "grade":
            return GRADE_ORDER.get(record.grade, 99)
        if sort_by == "company":
            return record.company.lower()
        if sort_by == "score":
            try:
                return -float(record.score)
            except (TypeError, ValueError):
                return 0.0
        return record.date

    return sorted(records, key=sort_key, reverse=(sort_by == "date"))


def filter_records(records: list[JobRecord], filter_name: str) -> list[JobRecord]:
    if filter_name == "a_plus":
        return [r for r in records if grade_passes(r.grade, "A")]
    if filter_name == "b_plus":
        return [r for r in records if grade_passes(r.grade, "B+")]
    if filter_name == "to_apply":
        return [r for r in records if r.ready_to_apply]
    if filter_name == "applied":
        return [r for r in records if (r.status or "").lower() == "applied"]
    if filter_name == "callback":
        return [r for r in records if (r.status or "").lower() == "callback"]
    if filter_name == "interview":
        return [r for r in records if (r.status or "").lower() == "interview"]
    if filter_name == "rejected":
        return [r for r in records if (r.status or "").lower() in {"rejected", "sponsorship_fail", "seniority_fail"}]
    return list(records)


def load_dashboard_records(sort_by: str = "date") -> list[JobRecord]:
    tracker_rows = load_tsv(TRACKER)
    source_index = build_index(load_tsv(SOURCE_HISTORY), "target_url")
    scan_index = build_index(load_tsv(SCAN_HISTORY), "url")
    records: list[JobRecord] = []

    for row in tracker_rows:
        status, rejection_reason = normalize_record_status(
            row.get("status", ""),
            row.get("notes", ""),
        )
        notes = row.get("notes", "").strip()
        if rejection_reason:
            notes = upsert_rejection_reason(notes, rejection_reason)

        url = row.get("url", "").strip()
        pdf_path = row.get("pdf_path", "").strip()
        cv_exists = bool(pdf_path) and (REPO_ROOT / pdf_path).exists()
        scan_row = scan_index.get(url, {})
        jd_src = notes if notes in ("REAL", "MOCK") else "?"
        spons = "FAIL" if rejection_reason == "sponsorship_fail" else "PASS"
        ready_to_apply = status == "cv_ready" and cv_exists and spons == "PASS"

        records.append(
            JobRecord(
                date=row.get("date", "").strip(),
                grade=row.get("grade", "?").strip(),
                score=row.get("score", "?").strip(),
                source=infer_source(url, source_index),
                jd_src=jd_src,
                spons=spons,
                cv="yes" if cv_exists else "no",
                ofe="?",
                con="?",
                company=row.get("company", "?").strip(),
                role=row.get("role", "?").strip(),
                status=status,
                url=url,
                notes=notes,
                eval_path=scan_row.get("eval_path", "").strip(),
                eval_excerpt="",
                cv_path=pdf_path if cv_exists else "",
                oferta_path="",
                outreach_path="",
                ready_to_apply=ready_to_apply,
            )
        )

    return sort_records(records, sort_by)


def load_dashboard_record_summary(url: str) -> str:
    tracker_rows = load_tsv(TRACKER)
    row = next((item for item in tracker_rows if item.get("url", "").strip() == url.strip()), None)
    if row is None:
        return ""

    scan_index = build_index(load_tsv(SCAN_HISTORY), "url")
    eval_path = find_eval(row, scan_index)
    if eval_path is None:
        return ""

    excerpt = extract_markdown_section(eval_path, ["## Verdict", "## 1. Executive Summary"])
    return excerpt


def _build_enriched_job_record(
    row: dict,
    source_index: dict[str, dict],
    scan_index: dict[str, dict],
    artifact_index: dict[str, dict],
    eval_job_keys: dict[str, str],
    rows_by_company_date: dict[tuple[str, str], list[dict]],
) -> JobRecord:
    company = row.get("company", "?").strip()
    role = row.get("role", "?").strip()
    url = row.get("url", "").strip()
    raw_status = row.get("status", "").strip()
    notes = row.get("notes", "").strip()
    source = infer_source(url, source_index)
    eval_path = find_eval(row, scan_index)
    related_rows = rows_by_company_date.get(_company_date_key(row), [])

    if raw_status == "sponsorship_fail":
        jd_src, spons = notes if notes in ("REAL", "MOCK") else "?", "FAIL"
        jd_src, _ = read_eval_meta(eval_path, notes)
    else:
        jd_src, spons = read_eval_meta(eval_path, notes)

    oferta_path = resolve_related_artifact(
        row, company, role, related_rows, EVALS_DIR, "deep_{slug}_*.md", artifact_index, eval_job_keys
    )
    outreach_path = resolve_related_artifact(
        row, company, role, related_rows, APPLICATIONS, "outreach_{slug}_*.md", artifact_index, eval_job_keys
    )
    cv_path = resolve_cv_path(row, company, role, related_rows, artifact_index, eval_job_keys)

    excerpt = extract_markdown_section(oferta_path, ["## 1. Executive Summary"])
    if not excerpt:
        excerpt = extract_markdown_section(eval_path, ["## Verdict", "## 1. Executive Summary"])

    has_cv = "yes" if cv_path else "no"
    has_ofe = "yes" if oferta_path else "no"
    has_con = "yes" if outreach_path else "no"
    ready_to_apply = has_cv == "yes" and has_ofe == "yes" and has_con == "yes" and spons == "PASS"

    return JobRecord(
        date=row.get("date", "").strip(),
        grade=row.get("grade", "?").strip(),
        score=row.get("score", "?").strip(),
        source=source,
        jd_src=jd_src,
        spons=spons,
        cv=has_cv,
        ofe=has_ofe,
        con=has_con,
        company=company,
        role=role,
        status=raw_status,
        url=url,
        notes=notes,
        eval_path=str(eval_path.relative_to(REPO_ROOT)) if eval_path else "",
        eval_excerpt=excerpt,
        cv_path=str(cv_path.relative_to(REPO_ROOT)) if cv_path else "",
        oferta_path=str(oferta_path.relative_to(REPO_ROOT)) if oferta_path else "",
        outreach_path=str(outreach_path.relative_to(REPO_ROOT)) if outreach_path else "",
        ready_to_apply=ready_to_apply,
    )


def load_dashboard_record_detail(url: str) -> JobRecord | None:
    tracker_rows = load_tsv(TRACKER)
    row = next((item for item in tracker_rows if item.get("url", "").strip() == url.strip()), None)
    if row is None:
        return None

    source_index = build_index(load_tsv(SOURCE_HISTORY), "target_url")
    scan_rows = load_tsv(SCAN_HISTORY)
    scan_index = build_index(scan_rows, "url")
    artifact_index = load_artifact_index()
    eval_job_keys = build_eval_job_key_map(tracker_rows, scan_rows)
    rows_by_company_date: dict[tuple[str, str], list[dict]] = {}
    for tracker_row in tracker_rows:
        rows_by_company_date.setdefault(_company_date_key(tracker_row), []).append(tracker_row)

    return _build_enriched_job_record(
        row,
        source_index,
        scan_index,
        artifact_index,
        eval_job_keys,
        rows_by_company_date,
    )


def load_job_records(sort_by: str = "date") -> list[JobRecord]:
    tracker_rows = load_tsv(TRACKER)
    source_index = build_index(load_tsv(SOURCE_HISTORY), "target_url")
    scan_rows = load_tsv(SCAN_HISTORY)
    scan_index = build_index(scan_rows, "url")
    artifact_index = load_artifact_index()
    eval_job_keys = build_eval_job_key_map(tracker_rows, scan_rows)
    rows_by_company_date: dict[tuple[str, str], list[dict]] = {}
    for tracker_row in tracker_rows:
        rows_by_company_date.setdefault(_company_date_key(tracker_row), []).append(tracker_row)

    records: list[JobRecord] = []
    for row in tracker_rows:
        records.append(
            _build_enriched_job_record(
                row,
                source_index,
                scan_index,
                artifact_index,
                eval_job_keys,
                rows_by_company_date,
            )
        )

    return sort_records(records, sort_by)


def update_tracker_status(url: str, status: str) -> bool:
    rows = load_tsv(TRACKER)
    changed = False
    for row in rows:
        if row.get("url", "").strip() == url.strip():
            if status == "sponsorship_fail":
                row["status"] = "rejected"
                row["notes"] = upsert_rejection_reason(row.get("notes", ""), "sponsorship_fail")
            elif status == "seniority_fail":
                row["status"] = "rejected"
                row["notes"] = upsert_rejection_reason(row.get("notes", ""), "seniority_fail")
            elif status == "rejected":
                row["status"] = "rejected"
                row["notes"] = upsert_rejection_reason(row.get("notes", ""), "")
            else:
                row["status"] = status
                row["notes"] = upsert_rejection_reason(row.get("notes", ""), "")
            changed = True
            break

    if not changed:
        return False

    write_tsv(TRACKER, rows, TRACKER_HEADER)
    return True
