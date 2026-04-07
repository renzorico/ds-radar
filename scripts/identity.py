"""
Minimal job/artifact identity helpers for ds-radar.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_INDEX = REPO_ROOT / "artifacts-index.jsonl"


def normalize_label(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def canonicalize_job_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""

    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+", "/", unquote(parts.path or "").strip()).rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def build_job_key(url: str = "", company: str = "", title: str = "") -> str:
    canonical_url = canonicalize_job_url(url)
    company_key = normalize_label(company)
    title_key = normalize_label(title)
    parts = [part for part in (canonical_url, company_key, title_key) if part]
    if not parts:
        return ""
    digest = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def load_artifact_index() -> dict[str, dict]:
    if not ARTIFACT_INDEX.exists():
        return {}

    entries: dict[str, dict] = {}
    with ARTIFACT_INDEX.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            rel_path = entry.get("artifact_path", "").strip()
            if rel_path:
                entries[rel_path] = entry
    return entries


def record_artifact_identity(
    artifact_path: Path,
    *,
    url: str = "",
    company: str = "",
    title: str = "",
    source_eval: str = "",
) -> None:
    artifact_path = artifact_path.resolve()
    try:
        rel_path = str(artifact_path.relative_to(REPO_ROOT))
    except ValueError:
        rel_path = str(artifact_path)

    entries = load_artifact_index()
    entries[rel_path] = {
        "artifact_path": rel_path,
        "job_key": build_job_key(url=url, company=company, title=title),
        "url": canonicalize_job_url(url),
        "company": company.strip(),
        "title": title.strip(),
        "source_eval": source_eval.strip(),
    }

    ARTIFACT_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with ARTIFACT_INDEX.open("w", encoding="utf-8") as handle:
        for key in sorted(entries):
            handle.write(json.dumps(entries[key], ensure_ascii=False) + "\n")


def parse_artifact_metadata(path: Path) -> dict[str, str]:
    if not path.exists() or path.suffix.lower() != ".md":
        return {}

    try:
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12])
    except OSError:
        return {}

    data: dict[str, str] = {}
    patterns = {
        "job_key": r"Job key:\s*([0-9a-f]{16})",
        "source_eval": r"Source eval:\s*([^\s|>]+\.md)",
        "url": r"\*\*URL:\*\*\s*([^|\n]+)",
        "deep_title_company": r"^#\s+DEEP ANALYSIS:\s+(.+?)\s+@\s+(.+)$",
        "outreach_company_title": r"^#\s+OUTREACH:\s+(.+?)\s+—\s+(.+)$",
    }

    match = re.search(patterns["job_key"], head, re.IGNORECASE)
    if match:
        data["job_key"] = match.group(1).strip()

    match = re.search(patterns["source_eval"], head, re.IGNORECASE)
    if match:
        data["source_eval"] = match.group(1).strip()

    match = re.search(patterns["url"], head, re.IGNORECASE)
    if match:
        data["url"] = match.group(1).strip()

    match = re.search(patterns["deep_title_company"], head, re.MULTILINE)
    if match:
        data["title"] = match.group(1).strip()
        data["company"] = match.group(2).strip()
    else:
        match = re.search(patterns["outreach_company_title"], head, re.MULTILINE)
        if match:
            data["company"] = match.group(1).strip()
            data["title"] = match.group(2).strip()

    return data


def artifact_job_key(
    path: Path,
    artifact_index: dict[str, dict] | None = None,
    eval_job_keys: dict[str, str] | None = None,
) -> str:
    try:
        rel_path = str(path.relative_to(REPO_ROOT))
    except ValueError:
        rel_path = str(path)

    if artifact_index:
        entry = artifact_index.get(rel_path)
        if entry and entry.get("job_key"):
            return entry["job_key"].strip()

    if path.suffix.lower() != ".md":
        sibling_markdown = path.with_suffix(".md")
        if sibling_markdown.exists():
            sibling_key = artifact_job_key(sibling_markdown, artifact_index, eval_job_keys)
            if sibling_key:
                return sibling_key

    metadata = parse_artifact_metadata(path)
    if metadata.get("job_key"):
        return metadata["job_key"]

    if metadata.get("url"):
        return build_job_key(
            url=metadata["url"],
            company=metadata.get("company", ""),
            title=metadata.get("title", ""),
        )

    source_eval = metadata.get("source_eval", "")
    if source_eval and eval_job_keys:
        for key in (source_eval, f"evals/{source_eval}"):
            job_key = eval_job_keys.get(key, "")
            if job_key:
                return job_key

    return ""
