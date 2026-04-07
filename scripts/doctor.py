"""
ds-radar health diagnostic
Usage: python scripts/doctor.py

Read-only. Checks runtime prerequisites, config, and state files.
Exit 0 — no FAILs. Exit 1 — at least one FAIL.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_fails = 0


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    global _fails
    _fails += 1
    print(f"  [FAIL] {msg}")


# ── Python version ────────────────────────────────────────────────────────────

print("\nPython")
vi = sys.version_info
if vi >= (3, 10):
    ok(f"Python {vi.major}.{vi.minor}.{vi.micro}")
else:
    fail(f"Python {vi.major}.{vi.minor}.{vi.micro} — 3.10+ required")


# ── .env and API key ──────────────────────────────────────────────────────────

print("\nEnvironment")
env_path = REPO_ROOT / ".env"
if env_path.exists():
    ok(".env found")
else:
    fail(".env not found — create it with ANTHROPIC_API_KEY=sk-...")

# Load .env manually (avoid depending on dotenv for the key check itself)
import os
_raw_env: dict[str, str] = {}
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            _raw_env[k.strip()] = v.strip().strip('"').strip("'")

api_key = os.environ.get("ANTHROPIC_API_KEY") or _raw_env.get("ANTHROPIC_API_KEY", "")
if api_key:
    ok(f"ANTHROPIC_API_KEY present ({api_key[:8]}…)")
else:
    fail("ANTHROPIC_API_KEY missing or empty")


# ── Python imports ────────────────────────────────────────────────────────────

print("\nDependencies")
_import_checks = [
    ("anthropic",  "anthropic"),
    ("yaml",       "pyyaml"),
    ("dotenv",     "python-dotenv"),
    ("markdown",   "markdown"),
]
for module, pkg in _import_checks:
    try:
        __import__(module)
        ok(f"{module}")
    except ImportError:
        fail(f"{module} not importable — pip install {pkg}")

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    ok("playwright.sync_api")
except ImportError:
    fail("playwright not importable — pip install playwright && playwright install chromium")


# ── Profile files ─────────────────────────────────────────────────────────────

print("\nProfile")
profile_path = REPO_ROOT / "profile" / "profile.yaml"
if not profile_path.exists():
    fail(f"profile/profile.yaml not found")
else:
    ok("profile/profile.yaml found")
    try:
        import yaml
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        required_keys = ["identity", "experience", "compensation", "target_roles", "scoring_weights"]
        for key in required_keys:
            if profile.get(key):
                ok(f"  profile.{key} present")
            else:
                fail(f"  profile.{key} missing or empty")
    except Exception as e:
        fail(f"profile/profile.yaml parse error: {e}")

companies_path = REPO_ROOT / "profile" / "target-companies.yaml"
if not companies_path.exists():
    fail("profile/target-companies.yaml not found")
else:
    try:
        import yaml
        data = yaml.safe_load(companies_path.read_text(encoding="utf-8")) or {}
        companies = data.get("companies", [])
        if companies:
            ok(f"target-companies.yaml — {len(companies)} compan{'y' if len(companies) == 1 else 'ies'}")
        else:
            fail("target-companies.yaml has no company entries")
    except Exception as e:
        fail(f"target-companies.yaml parse error: {e}")


# ── Output directories ────────────────────────────────────────────────────────

print("\nDirectories")
for dirname in ("evals", "applications"):
    d = REPO_ROOT / dirname
    if d.is_dir():
        ok(f"{dirname}/")
    else:
        fail(f"{dirname}/ not found — mkdir {dirname}")


# ── State files ───────────────────────────────────────────────────────────────

print("\nState files")
state_files = [
    ("scan-history.tsv", "scan history — run scan.py to populate"),
    ("tracker.tsv",      "tracker — will be created on first pipeline run"),
    ("scan-queue.txt",   "scan queue — run scan.py to populate"),
]
for filename, hint in state_files:
    p = REPO_ROOT / filename
    if p.exists():
        size = p.stat().st_size
        ok(f"{filename} ({size} bytes)")
    else:
        warn(f"{filename} not found — {hint}")


# ── Summary ───────────────────────────────────────────────────────────────────

print()
if _fails == 0:
    print("  ds-radar is ready.\n")
    sys.exit(0)
else:
    print(f"  {_fails} check(s) failed. Fix the issues above before running the pipeline.\n")
    sys.exit(1)
