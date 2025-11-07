#!/usr/bin/env python3
"""Automated test addition and PR preparation for multiple repositories.

Reimplements the logic from `run_success_flow.sh` in Python, allowing
batch processing across several repositories under the same GitHub account.

Default GitHub account: roapi-cloud
Default repositories: claude_agent1, claude_agent2, claude_agent3

Flow per repository:
1. Clone via SSH.
2. Create feature branch (auto/<task_id>).
3. Create virtual environment & install requirements.
4. Run baseline coverage.
5. Inject new test file (payment tests example).
6. Run ruff, mypy (tolerate failures), then tests + coverage.
7. Capture diff stats, coverage reports, PR body.
8. Commit & push branch.
9. Optionally create PR using GitHub CLI (`gh`).

Artifacts stored under: artifacts/<task_id>/ inside each repository clone.

Usage examples:
    python docs/samples/run_success_flow.py \
        --repos claude_agent1 claude_agent2 \
        --task-id add-payment-tests \
        --module-path src/service/payment.py \
        --create-pr

Note: The test assumes a callable `calculate_fee` in module path
`src/service/payment.py`. Adjust `--module-path` or provide a custom test
template with `--test-file`. If the path doesn't exist, the script will warn
and skip injecting tests (but still create artifacts and push branch).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from git import Repo


@dataclass
class RepoConfig:
    account: str
    name: str
    task_id: str
    branch: str
    ssh_url: str


def run_command(cmd: List[str], cwd: Path | None = None, allow_fail: bool = False) -> subprocess.CompletedProcess:
    """Run a command and stream output; optionally tolerate failure."""
    print(f"[CMD] {' '.join(cmd)} (cwd={cwd or Path.cwd()})")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=not allow_fail, text=True, capture_output=True)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            # Only show stderr if non-empty and not purely benign warnings.
            print(result.stderr.rstrip())
        return result
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {e}; returncode={e.returncode}")
        if not allow_fail:
            raise
        return e


def ensure_venv(repo_dir: Path) -> Path:
    venv_dir = repo_dir / ".venv"
    if not venv_dir.exists():
        run_command([sys.executable, "-m", "venv", str(venv_dir)], cwd=repo_dir)
    # Activation script path returned for informational purposes.
    return venv_dir


def pip_install_requirements(repo_dir: Path, python_bin: Path) -> None:
    req_file = repo_dir / "requirements.txt"
    if req_file.exists():
        run_command([str(python_bin), "-m", "pip", "install", "-r", str(req_file)], cwd=repo_dir, allow_fail=False)
    else:
        print("[WARN] requirements.txt not found; skipping dependency installation.")


def write_test_file(repo_dir: Path, module_path: str, test_path: Path, custom_content: str | None) -> bool:
    src_module = repo_dir / module_path
    if not src_module.exists():
        print(f"[WARN] Module path '{module_path}' not found in {repo_dir}; skipping test injection.")
        return False
    test_dir = test_path.parent
    test_dir.mkdir(parents=True, exist_ok=True)
    if custom_content is None:
        content = (
            "import pytest\n"
            f"from {module_path.replace('/', '.').rstrip('.py')} import calculate_fee\n\n"
            "def test_positive_fee():\n"
            "    assert calculate_fee(100) == pytest.approx(100 * 0.05)\n\n"
            "def test_zero_fee():\n"
            "    assert calculate_fee(0) == 0\n"
        )
    else:
        content = custom_content
    test_path.write_text(content, encoding="utf-8")
    print(f"[INFO] Wrote test file: {test_path}")
    return True


def compute_diff_stats(repo: Repo) -> str:
    try:
        return repo.git.diff('--shortstat')
    except Exception as e:
        print(f"[WARN] Failed to compute diff stats: {e}")
        return ""


def create_pr_body(artifacts_dir: Path, task_id: str, coverage_improvement: str | None) -> Path:
    pr_file = artifacts_dir / "pr.md"
    lines = ["## feat(test): add payment tests (auto)", "增加 payment 模块测试；提升基础覆盖率。", "自动任务执行成功。"]
    if coverage_improvement:
        lines.append("\n### 覆盖率提升\n" + coverage_improvement)
    pr_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"[INFO] Generated PR body: {pr_file}")
    return pr_file


def parse_coverage_delta(baseline: Path, current: Path) -> str | None:
    try:
        b = baseline.read_text(encoding="utf-8")
        c = current.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    # Naive approach: include last line from each report.
    b_last = [ln for ln in b.splitlines() if ln.strip()][-1]
    c_last = [ln for ln in c.splitlines() if ln.strip()][-1]
    return f"Baseline: {b_last}\nCurrent: {c_last}"


def maybe_create_pr(repo_dir: Path, branch: str, pr_body: Path, create_pr: bool, base_branch: str) -> None:
    if not create_pr:
        print("[INFO] Skipping PR creation (flag not set). Use gh pr create manually if desired.")
        return
    # Check if gh is available.
    if shutil.which("gh") is None:
        print("[WARN] GitHub CLI 'gh' not found; cannot auto-create PR.")
        return
    print("[INFO] Creating PR via GitHub CLI")
    run_command([
        "gh",
        "pr",
        "create",
        "--title",
        "feat(test): add payment tests (auto)",
        "--body-file",
        str(pr_body),
        "--label",
        "automated",
        "--label",
        "test",
        "--base",
        base_branch,
        "--head",
        branch,
    ], cwd=repo_dir, allow_fail=True)


def process_repository(cfg: RepoConfig, args: argparse.Namespace) -> None:
    print(f"\n[INFO] === Processing repository: {cfg.name} ===")
    clone_dir = Path(cfg.name)
    if clone_dir.exists():
        print("[INFO] Removing existing directory for fresh clone")
        shutil.rmtree(clone_dir)
    try:
        repo = Repo.clone_from(cfg.ssh_url, str(clone_dir))
    except Exception as e:
        print(f"[ERROR] Failed to clone {cfg.ssh_url}: {e}")
        return

    # Handle empty repository
    if not repo.heads:
        print("[INFO] Repository is empty; creating initial commit")
        # Create basic structure
        readme = clone_dir / "README.md"
        readme.write_text("# Test Repository\n", encoding="utf-8")
        req = clone_dir / "requirements.txt"
        req.write_text("pytest\n", encoding="utf-8")
        payment_dir = clone_dir / "src" / "service"
        payment_dir.mkdir(parents=True, exist_ok=True)
        payment_py = payment_dir / "payment.py"
        payment_py.write_text("def calculate_fee(amount):\n    return amount * 0.05\n", encoding="utf-8")
        # Add and commit
        repo.index.add(['README.md', 'requirements.txt', 'src/service/payment.py'])
        repo.index.commit("Initial commit")
        # Create master branch
        repo.git.checkout('-b', 'master')
        repo.git.push('origin', 'master')  # Push initial branch
        default_branch = 'master'
    else:
        # Git operations for non-empty repo
        try:
            repo.git.fetch('origin')
            # Determine default branch
            try:
                default_branch = repo.git.symbolic_ref('refs/remotes/origin/HEAD').split('/')[-1]
            except:
                # Fallback: try main, then master
                try:
                    repo.git.checkout('main')
                    default_branch = 'main'
                except:
                    repo.git.checkout('master')
                    default_branch = 'master'
            if default_branch != repo.active_branch.name:
                repo.git.checkout(default_branch)
            repo.git.pull('origin', default_branch, '--ff-only')
        except Exception as e:
            print(f"[ERROR] Git operations failed: {e}")
            return

    # Create feature branch
    try:
        repo.git.checkout('-b', cfg.branch)
    except Exception as e:
        print(f"[ERROR] Failed to create branch {cfg.branch}: {e}")
        return

    # Virtual environment & dependencies
    venv_dir = ensure_venv(clone_dir)
    python_bin = venv_dir / "bin" / "python"
    pip_install_requirements(clone_dir, python_bin)

    artifacts_dir = clone_dir / "artifacts" / cfg.task_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Baseline coverage
    run_command([str(python_bin), "-m", "coverage", "run", "-m", "pytest", "-q"], cwd=clone_dir, allow_fail=True)
    run_command([str(python_bin), "-m", "coverage", "report", "-m"], cwd=clone_dir, allow_fail=True)
    baseline_cov = artifacts_dir / "baseline_coverage.txt"
    cov_out = run_command([str(python_bin), "-m", "coverage", "report", "-m"], cwd=clone_dir, allow_fail=True)
    baseline_cov.write_text((cov_out.stdout or "").strip(), encoding="utf-8")

    # Inject test
    test_injected = write_test_file(
        clone_dir,
        args.module_path,
        clone_dir / "tests" / "test_payment.py",
        args.test_file.read_text(encoding="utf-8") if args.test_file else None,
    )

    # Quality checks
    run_command([str(python_bin), "-m", "ruff", "check", "src", "tests"], cwd=clone_dir, allow_fail=True)
    run_command([str(python_bin), "-m", "mypy", "src", "--ignore-missing-imports"], cwd=clone_dir, allow_fail=True)

    # Current coverage
    run_command([str(python_bin), "-m", "coverage", "run", "-m", "pytest", "-q"], cwd=clone_dir, allow_fail=True)
    current_cov = artifacts_dir / "current_coverage.txt"
    cov_out2 = run_command([str(python_bin), "-m", "coverage", "report", "-m"], cwd=clone_dir, allow_fail=True)
    current_cov.write_text((cov_out2.stdout or "").strip(), encoding="utf-8")

    # Diff stats
    diff_stats = compute_diff_stats(repo)
    (artifacts_dir / "diff.txt").write_text(diff_stats, encoding="utf-8")

    # Git add + commit + push (only if test injected or test file content provided)
    try:
        if test_injected:
            repo.index.add(['tests/test_payment.py', str(artifacts_dir)])
        else:
            repo.index.add([str(artifacts_dir)])
        repo.index.commit("test: add payment tests (auto)")
        repo.git.push('origin', cfg.branch)
    except Exception as e:
        print(f"[ERROR] Git commit/push failed: {e}")
        return

    coverage_improvement = parse_coverage_delta(baseline_cov, current_cov)
    pr_body = create_pr_body(artifacts_dir, cfg.task_id, coverage_improvement)
    maybe_create_pr(clone_dir, cfg.branch, pr_body, args.create_pr, default_branch)
    print(f"[INFO] Completed repository: {cfg.name}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Automated test addition & PR preparation across multiple repos.")
    p.add_argument("--account", default="yuping322", help="GitHub account/organization name.")
    p.add_argument(
        "--repos",
        nargs="*",
        default=["claude_agent1", "claude_agent2", "claude_agent3"],
        help="List of repository names under the account.",
    )
    p.add_argument("--task-id", default="add-payment-tests", help="Task identifier used in branch & artifacts.")
    p.add_argument("--module-path", default="src/service/payment.py", help="Path to target module for tests.")
    p.add_argument("--create-pr", action="store_true", help="If set, attempt to create PR via GitHub CLI.")
    p.add_argument(
        "--test-file",
        type=Path,
        help="Optional path to a custom test file template. Overrides generated test content.",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    print(f"[INFO] Starting automation for account={args.account} repos={args.repos} task={args.task_id}")
    for repo in args.repos:
        cfg = RepoConfig(
            account=args.account,
            name=repo,
            task_id=args.task_id,
            branch=f"auto/{args.task_id}",
            ssh_url=f"git@github.com:{args.account}/{repo}.git",
        )
        try:
            process_repository(cfg, args)
        except Exception as e:
            print(f"[ERROR] Failed processing {repo}: {e}")
    print("\n[INFO] All done.")


if __name__ == "__main__":  # pragma: no cover
    main()
