"""
Manual sanity checks for ds-radar job/artifact identity.

Run with:
  python -m scripts.manual_identity_check
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.identity import artifact_job_key, build_job_key, canonicalize_job_url
from scripts.job_data import _artifact_matches_row, short_role_slug, slugify, url_job_slug


def pick_candidate(
    candidates: list[Path],
    *,
    url: str,
    company: str,
    role: str,
    artifact_index: dict[str, dict],
) -> Path | None:
    row_key = build_job_key(url=url, company=company, title=role)
    exact_matches: list[Path] = []
    heuristic_matches: list[Path] = []
    company_slug = slugify(company)
    role_slug = short_role_slug(role)
    job_slug = url_job_slug(url)

    for candidate in candidates:
        candidate_key = artifact_job_key(candidate, artifact_index, {})
        if row_key and candidate_key:
            if row_key == candidate_key:
                exact_matches.append(candidate)
            continue
        if _artifact_matches_row(candidate, company_slug, role_slug, job_slug):
            heuristic_matches.append(candidate)

    if exact_matches:
        return exact_matches[0]
    if heuristic_matches:
        return heuristic_matches[0]
    return candidates[0] if candidates else None


def main() -> None:
    base_url = "https://www.linkedin.com/jobs/view/deliveroo-ml-job-123"
    noisy_url = "https://www.linkedin.com/jobs/view/deliveroo-ml-job-123?tracking=abc&utm_source=x#fragment"
    key_a = build_job_key(url=base_url, company="Deliveroo", title="Machine Learning Engineer")
    key_b = build_job_key(url=noisy_url, company="Deliveroo", title="Machine Learning Engineer")
    assert canonicalize_job_url(base_url) == canonicalize_job_url(noisy_url)
    assert key_a == key_b
    print("same-url-with-query-noise:", key_a == key_b, key_a)

    key_c = build_job_key(
        url="https://www.linkedin.com/jobs/view/role-1",
        company="Formula Recruitment",
        title="Artificial Intelligence Engineer",
    )
    key_d = build_job_key(
        url="https://www.linkedin.com/jobs/view/role-2",
        company="Formula Recruitment",
        title="Analytics Consultant",
    )
    assert key_c != key_d
    print("similar-roles-same-company-differ:", key_c != key_d, key_c, key_d)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / "cv_formula-recruitment_20260407.pdf"
        old_md_path = tmp_path / "cv_formula-recruitment_20260402.md"
        pdf_path.write_text("pdf placeholder", encoding="utf-8")
        old_md_path.write_text("md placeholder", encoding="utf-8")

        target_url = "https://uk.linkedin.com/jobs/view/artificial-intelligence-engineer-at-formula-recruitment-4378762094"
        target_key = build_job_key(
            url=target_url,
            company="Formula Recruitment",
            title="Artificial Intelligence Engineer",
        )
        artifact_index = {
            str(pdf_path): {
                "artifact_path": str(pdf_path),
                "job_key": target_key,
            }
        }
        preferred = pick_candidate(
            [pdf_path, old_md_path],
            url=target_url,
            company="Formula Recruitment",
            role="Artificial Intelligence Engineer",
            artifact_index=artifact_index,
        )
        assert preferred == pdf_path
        print("multiple-cv-variants-prefers-job-key:", preferred.name)

        heuristic_only = tmp_path / "outreach_version-1_2026-04-02.md"
        heuristic_only.write_text("placeholder", encoding="utf-8")
        fallback = pick_candidate(
            [heuristic_only],
            url="https://uk.linkedin.com/jobs/view/analytics-consultant-at-version-1-4376203362",
            company="Version 1",
            role="Analytics Consultant",
            artifact_index={},
        )
        assert fallback == heuristic_only
        print("no-identity-falls-back-to-heuristic:", fallback.name)

    print("manual identity checks passed")


if __name__ == "__main__":
    main()
