#!/usr/bin/env python3
"""Release pipeline for paircode + its satellite repos.

Usage:
    ./scripts/release.py 0.10.0          # explicit version
    ./scripts/release.py patch           # auto-bump the patch segment
    ./scripts/release.py minor
    ./scripts/release.py major
    ./scripts/release.py --dry-run 0.10.0  # show what would happen

One script that:
    1. Validates working tree is clean, tests pass
    2. Bumps paircode version in pyproject.toml + __init__.py
    3. Commits + tags paircode, pushes to GitHub
    4. Publishes paircode to pypi via `starforge beam --pypi`
    5. Syncs templates → satellite repos (paircode-codex, paircode-gemini)
    6. Bumps each satellite's manifest version
    7. Commits + tags each satellite, pushes to GitHub
    8. Creates GitHub releases (gh release create) on each satellite
       — critical for Gemini's release-lookup, which falls back to an
       interactive prompt when no release exists

One command keeps pypi, the main GitHub repo, and both satellites
version-locked.

Assumptions:
    * Main paircode repo at  ~/dev/paircode
    * paircode-codex  repo at  ~/dev/paircode-codex  (cloned locally)
    * paircode-gemini repo at  ~/dev/paircode-gemini  (cloned locally)
    * starforge on PATH (`brew install starshipagentic/tap/starforge`)
    * gh on PATH (GitHub CLI) with auth
    * GITHUB_TOKEN unset in the shell so gh uses keyring (see README note)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PAIRCODE_ROOT = Path.home() / "dev" / "paircode"
CODEX_SATELLITE = Path.home() / "dev" / "paircode-codex"
GEMINI_SATELLITE = Path.home() / "dev" / "paircode-gemini"


@dataclass
class Repo:
    name: str
    path: Path
    version_files: list[tuple[Path, str, str]]  # (file, search_pattern, template)
    template_syncs: list[tuple[str, str]]       # (source-under-paircode, dest-under-repo)
    commit_msg_prefix: str
    gh_release_notes: str


PAIRCODE_REPO = Repo(
    name="paircode",
    path=PAIRCODE_ROOT,
    version_files=[
        (
            PAIRCODE_ROOT / "pyproject.toml",
            r'(?m)^version = "[^"]+"',
            'version = "{version}"',
        ),
        (
            PAIRCODE_ROOT / "src" / "paircode" / "__init__.py",
            r'__version__ = "[^"]+"',
            '__version__ = "{version}"',
        ),
    ],
    template_syncs=[],
    commit_msg_prefix="release",
    gh_release_notes="See CHANGELOG.md for details.",
)

CODEX_REPO = Repo(
    name="paircode-codex",
    path=CODEX_SATELLITE,
    version_files=[
        (
            CODEX_SATELLITE / "plugins" / "paircode" / ".codex-plugin" / "plugin.json",
            r'"version": "[^"]+"',
            '"version": "{version}"',
        ),
    ],
    template_syncs=[
        ("src/paircode/templates/codex_slash_command.md",
         "plugins/paircode/commands/paircode.md"),
    ],
    commit_msg_prefix="sync to paircode",
    gh_release_notes="Synced to match paircode v{version}.",
)

GEMINI_REPO = Repo(
    name="paircode-gemini",
    path=GEMINI_SATELLITE,
    version_files=[
        (
            GEMINI_SATELLITE / "gemini-extension.json",
            r'"version": "[^"]+"',
            '"version": "{version}"',
        ),
    ],
    template_syncs=[
        ("src/paircode/templates/gemini_slash_command.toml",
         "commands/paircode.toml"),
    ],
    commit_msg_prefix="sync to paircode",
    gh_release_notes="Synced to match paircode v{version}.",
)

SATELLITES = [CODEX_REPO, GEMINI_REPO]


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path | None = None, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a command, stream output to stdout. Raises on non-zero if check=True."""
    print(f"\n    $ {' '.join(cmd)}  (cwd={cwd or Path.cwd()})")
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, env=env)
    return result


def run_capture(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command, return stripped stdout."""
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def env_no_github_token() -> dict:
    """Return os.environ copy with GITHUB_TOKEN removed — gh uses keyring."""
    env = dict(os.environ)
    env.pop("GITHUB_TOKEN", None)
    return env


# ---------------------------------------------------------------------------
# Version math
# ---------------------------------------------------------------------------

def current_version(repo: Repo) -> str:
    """Parse the version out of the first version_file."""
    path, pattern, _ = repo.version_files[0]
    text = path.read_text(encoding="utf-8")
    m = re.search(r'(?:version|__version__)\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not m:
        sys.exit(f"Could not find current version in {path}")
    return m.group(1)


def compute_next_version(current: str, bump: str) -> str:
    """Bump a semver string per the given bump (major/minor/patch)."""
    major, minor, patch = (int(x) for x in current.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    # Assume it's already an explicit version string like "0.10.0"
    if re.fullmatch(r"\d+\.\d+\.\d+", bump):
        return bump
    sys.exit(f"Invalid version bump: {bump}")


def write_version(repo: Repo, version: str, dry_run: bool = False) -> None:
    """Update every version_file in the repo."""
    for path, pattern, template in repo.version_files:
        text = path.read_text(encoding="utf-8")
        new_line = template.format(version=version)
        updated = re.sub(pattern, new_line, text, count=1)
        if updated == text:
            print(f"  ! no change in {path}; pattern not matched or version already set")
        else:
            print(f"  ✓ {path} → {new_line.strip()}")
            if not dry_run:
                path.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(repos: list[Repo]) -> None:
    """Bail if any repo isn't clean, a dep isn't installed, or tests fail."""
    for tool in ("git", "starforge", "gh"):
        if not shutil.which(tool):
            sys.exit(f"missing dependency: `{tool}` not on PATH")

    for repo in repos:
        if not repo.path.exists():
            sys.exit(f"{repo.name}: repo not found at {repo.path}. Clone it or adjust the script.")
        status = run_capture(["git", "status", "--porcelain"], cwd=repo.path)
        if status:
            sys.exit(
                f"{repo.name}: working tree dirty. Commit or stash first:\n{status}"
            )

    print("Running paircode tests before release...")
    run([".venv/bin/python", "-m", "pytest", "-q"], cwd=PAIRCODE_ROOT)


# ---------------------------------------------------------------------------
# Per-repo steps
# ---------------------------------------------------------------------------

def sync_templates(repo: Repo, dry_run: bool) -> None:
    """Copy the paircode-side templates into the satellite repo."""
    for src_rel, dest_rel in repo.template_syncs:
        src = PAIRCODE_ROOT / src_rel
        dest = repo.path / dest_rel
        print(f"  ⇲ copy {src} → {dest}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def commit_tag_push(repo: Repo, version: str, dry_run: bool) -> None:
    """git add + commit + tag + push for a single repo."""
    status = run_capture(["git", "status", "--porcelain"], cwd=repo.path)
    if not status:
        print(f"  {repo.name}: nothing to commit (templates/version already match)")
    else:
        msg = f"{repo.commit_msg_prefix} v{version}"
        if dry_run:
            print(f"  [dry-run] would commit {repo.name}: {msg}")
        else:
            run(["git", "add", "-A"], cwd=repo.path)
            run(["git", "commit", "-m", msg], cwd=repo.path)

    tag = f"v{version}"
    existing_tags = run_capture(["git", "tag", "-l", tag], cwd=repo.path)
    if existing_tags == tag:
        print(f"  {repo.name}: tag {tag} already exists, skipping tag step")
    else:
        if dry_run:
            print(f"  [dry-run] would tag {repo.name}: {tag}")
        else:
            run(["git", "tag", "-a", tag, "-m", f"{repo.name} {tag}"], cwd=repo.path)

    if dry_run:
        print(f"  [dry-run] would push {repo.name} + tags")
    else:
        run(["git", "push", "origin", "main", "--tags"], cwd=repo.path, env=env_no_github_token())


def starforge_beam(repo: Repo, with_pypi: bool, dry_run: bool) -> None:
    """Beam the repo to GitHub via starforge. --pypi only for the main package."""
    cmd = ["starforge", "beam", str(repo.path), "--public"]
    if with_pypi:
        cmd.append("--pypi")
    if dry_run:
        print(f"  [dry-run] would run: yes | {' '.join(cmd)}")
        return
    # starforge prompts for pypi confirmation → pipe `yes`
    subprocess.run(
        f"yes | {' '.join(cmd)}", shell=True, check=True,
        env=env_no_github_token(),
    )


def gh_release_create(repo: Repo, version: str, dry_run: bool) -> None:
    """Create a GitHub release. Critical for Gemini's release-lookup which
    otherwise falls back to an interactive 'install via git clone?' prompt."""
    gh_repo = f"starshipagentic/{repo.name}"
    notes = repo.gh_release_notes.format(version=version)
    cmd = [
        "gh", "release", "create", f"v{version}",
        "--repo", gh_repo,
        "--title", f"v{version}",
        "--notes", notes,
    ]
    if dry_run:
        print(f"  [dry-run] would run: {' '.join(cmd)}")
        return
    # gh release may already exist from a retry — don't fail the whole script
    result = subprocess.run(cmd, env=env_no_github_token(), capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✓ created {gh_repo} release v{version}")
    elif "already exists" in result.stderr.lower():
        print(f"  ! {gh_repo} release v{version} already exists; skipping")
    else:
        sys.exit(f"gh release create failed for {gh_repo}:\n{result.stderr}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="explicit version (e.g., 0.10.0) OR 'patch'/'minor'/'major'")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen; change nothing")
    parser.add_argument("--skip-tests", action="store_true", help="skip preflight test run")
    args = parser.parse_args()

    all_repos = [PAIRCODE_REPO, *SATELLITES]

    print("== paircode release pipeline ==")
    if not args.skip_tests:
        preflight(all_repos)
    else:
        print("(skip_tests=True; skipping preflight checks)")

    current = current_version(PAIRCODE_REPO)
    next_ver = compute_next_version(current, args.version)
    print(f"\nCurrent paircode version: {current}")
    print(f"Target version:           {next_ver}")
    if args.dry_run:
        print("(dry-run — nothing will be written or pushed)")

    # STEP 1: bump + ship main paircode (pypi + GitHub)
    print(f"\n[1/3] Release main paircode → v{next_ver}")
    write_version(PAIRCODE_REPO, next_ver, args.dry_run)
    commit_tag_push(PAIRCODE_REPO, next_ver, args.dry_run)
    starforge_beam(PAIRCODE_REPO, with_pypi=True, dry_run=args.dry_run)

    # STEP 2: sync + release each satellite
    for repo in SATELLITES:
        print(f"\n[2/3] Sync + release satellite {repo.name} → v{next_ver}")
        sync_templates(repo, args.dry_run)
        write_version(repo, next_ver, args.dry_run)
        commit_tag_push(repo, next_ver, args.dry_run)
        starforge_beam(repo, with_pypi=False, dry_run=args.dry_run)
        gh_release_create(repo, next_ver, args.dry_run)

    # STEP 3: summary
    print(f"\n[3/3] Release complete. Summary:")
    print(f"  paircode         v{next_ver} → https://pypi.org/project/paircode/  and  https://github.com/starshipagentic/paircode")
    for repo in SATELLITES:
        print(f"  {repo.name:18}v{next_ver} → https://github.com/starshipagentic/{repo.name}/releases/tag/v{next_ver}")
    print("\nVerify on your machine:")
    print("  pipx install --force paircode")
    print("  paircode install                   # native-register via satellites")


if __name__ == "__main__":
    main()
