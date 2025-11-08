#!/usr/bin/env python3
"""
Git Helper - Git operations using GitPython library.

This module provides GitHelper class for managing Git repositories,
supporting operations like cloning, pulling, committing, and pushing.
"""

import re
import shutil
from pathlib import Path
from typing import Optional, List, Tuple
import logging

try:
    from git import Repo, RemoteProgress, InvalidGitRepositoryError, GitCommandError
    from git.exc import GitCommandError as GitError
    GITPYTHON_AVAILABLE = True
except ImportError:
    GITPYTHON_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("GitPython not available, falling back to subprocess")

logger = logging.getLogger(__name__)


class GitProgress(RemoteProgress):
    """Git 操作进度回调（用于克隆、拉取等操作）"""

    def update(self, op_code, cur_count, max_count=None, message=''):
        """更新进度"""
        if max_count:
            percent = (cur_count / max_count) * 100
            logger.debug(f"Git progress: {percent:.1f}% - {message}")
        else:
            logger.debug(f"Git progress: {cur_count} - {message}")


class GitHelper:
    """Git 操作辅助类，使用 GitPython 实现

    参考主项目 GitManager 的接口设计，但使用 GitPython 库实现
    """

    def __init__(self, workspace_path: Path):
        """初始化 GitHelper

        Args:
            workspace_path: 工作目录路径（可以是 Git 仓库或空目录）
        """
        self.workspace_path = Path(workspace_path).resolve()
        self.repo: Optional[Repo] = None

        # 如果路径存在且是 Git 仓库，初始化 Repo 对象
        if self.workspace_path.exists() and (self.workspace_path / ".git").exists():
            try:
                self.repo = Repo(str(self.workspace_path))
            except InvalidGitRepositoryError:
                logger.warning(f"Path {self.workspace_path} exists but is not a valid Git repository")
                self.repo = None
            except Exception as e:
                logger.error(f"Failed to initialize Git repository: {e}")
                self.repo = None

    def _ensure_repo(self) -> bool:
        """确保 Repo 对象已初始化

        Returns:
            是否成功初始化
        """
        if self.repo is not None:
            return True

        if not GITPYTHON_AVAILABLE:
            logger.error("GitPython is not available")
            return False

        # 如果目录不存在，创建它
        if not self.workspace_path.exists():
            self.workspace_path.mkdir(parents=True, exist_ok=True)

        # 如果已经是 Git 仓库，初始化 Repo
        if (self.workspace_path / ".git").exists():
            try:
                self.repo = Repo(str(self.workspace_path))
                return True
            except Exception as e:
                logger.error(f"Failed to initialize existing Git repository: {e}")
                return False

        return False

    def _repo_exists(self) -> bool:
        """检查是否为 Git 仓库"""
        return (self.workspace_path / ".git").exists()

    def _has_remote(self, name: str = "origin") -> bool:
        """检查是否存在指定名称的远程仓库"""
        if not self._ensure_repo():
            return False
        try:
            return name in [remote.name for remote in self.repo.remotes]
        except Exception:
            return False

    def _branch_exists(self, branch: str) -> bool:
        """检查分支是否存在

        参考主项目 GitManager._branch_exists 实现
        """
        if not self._ensure_repo():
            return False
        try:
            # 检查本地分支
            for ref in self.repo.refs:
                # ref.name 可能是 'refs/heads/main' 或 'origin/main'
                ref_name = ref.name.split('/')[-1]
                if ref_name == branch:
                    return True
            return False
        except Exception:
            return False

    def _get_current_branch(self) -> Optional[str]:
        """获取当前分支名称"""
        if not self._ensure_repo():
            return None
        try:
            return self.repo.active_branch.name
        except Exception:
            return None

    def _has_pending_changes(self) -> bool:
        """检查是否有待提交的更改

        参考主项目 GitManager._has_pending_changes 实现
        """
        if not self._ensure_repo():
            return False
        try:
            # 使用 GitPython 检查是否有未提交的更改
            # is_dirty() 检查工作区是否有修改
            # untracked_files=True 也检查未跟踪的文件
            return self.repo.is_dirty(untracked_files=True)
        except Exception:
            return False

    def _is_ignored(self, path: str) -> bool:
        """检查文件是否被 .gitignore 忽略

        参考主项目 GitManager._is_ignored 实现

        注意：GitPython 的 check_ignore 方法：
        - 如果文件被忽略，返回文件路径（非空字符串）
        - 如果文件不被忽略，返回空字符串
        - 如果出错，可能抛出异常
        """
        if not self._ensure_repo():
            return False
        try:
            # GitPython 的 check_ignore 方法
            # 如果文件被忽略，返回文件路径；如果不被忽略，返回空字符串
            result = self.repo.git.check_ignore(path)
            # 如果返回非空字符串，说明文件被忽略
            return bool(result.strip())
        except Exception:
            # 如果 check_ignore 抛出异常或返回空，说明文件不被忽略
            return False

    def _filter_tracked_paths(self, paths: List[str]) -> List[str]:
        """过滤被忽略的文件路径

        参考主项目 GitManager._filter_tracked_paths 实现
        """
        tracked: List[str] = []
        skipped: List[str] = []

        for path in paths:
            if self._is_ignored(path):
                skipped.append(path)
            else:
                tracked.append(path)

        if skipped:
            logger.debug(f"Skipping ignored paths: {skipped}")

        return tracked

    def validate_changes(self, files: List[str]) -> Tuple[bool, str]:
        """验证文件是否可以提交（检查 secrets 和语法错误）

        Args:
            files: 文件路径列表（相对于工作区）

        Returns:
            Tuple[is_valid, error_message]
        """
        issues = []

        for file in files:
            file_path = self.workspace_path / file

            if not file_path.exists():
                continue

            # 检查是否包含 secrets
            if self._contains_secrets(file_path):
                issues.append(f"Potential secret in {file}")

            # 检查 Python 语法
            if file.endswith(".py") and not self._validate_python_syntax(file_path):
                issues.append(f"Python syntax error in {file}")

        if issues:
            return False, "\n".join(issues)
        return True, "OK"

    def _contains_secrets(self, file_path: Path) -> bool:
        """检查文件是否包含潜在的 secrets

        参考主项目 GitManager._contains_secrets 实现
        """
        secret_patterns = [
            "PRIVATE_KEY",
            "API_KEY",
            "PASSWORD",
            "SECRET",
            "TOKEN",
            "credential",
        ]

        try:
            content = file_path.read_text()
            for pattern in secret_patterns:
                if pattern in content.upper():
                    return True
        except Exception:
            pass
        return False

    def _validate_python_syntax(self, file_path: Path) -> bool:
        """验证 Python 文件语法

        参考主项目 GitManager._validate_python_syntax 实现
        """
        try:
            import ast
            ast.parse(file_path.read_text())
            return True
        except Exception:
            return False

    def configure_user(self, name: str = "Sleepless Agent", email: str = "agent@sleepless.local"):
        """配置 Git 用户信息"""
        if not self._ensure_repo():
            return
        try:
            with self.repo.config_writer() as cw:
                cw.set_value("user", "name", name)
                cw.set_value("user", "email", email)
            logger.debug(f"Configured Git user: {name} <{email}>")
        except Exception as e:
            logger.warning(f"Failed to configure git user: {e}")

    def checkout_branch(self, branch: str, create: bool = False) -> bool:
        """切换到分支

        Args:
            branch: 分支名称
            create: 如果分支不存在，是否创建

        Returns:
            是否成功
        """
        if not self._ensure_repo():
            return False

        try:
            if create and not self._branch_exists(branch):
                # 创建新分支
                current_branch = self._get_current_branch()
                if current_branch:
                    self.repo.git.checkout("-b", branch)
                else:
                    self.repo.git.checkout("-b", branch, "HEAD")
                logger.info(f"Created and checked out branch: {branch}")
            else:
                # 切换到现有分支
                self.repo.git.checkout(branch)
                logger.info(f"Checked out branch: {branch}")
            return True
        except GitError as e:
            logger.error(f"Failed to checkout branch {branch}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking out branch {branch}: {e}")
            return False

    def pull_latest(self, repo_url: str, branch: str, token: Optional[str] = None, use_worktree: bool = True, shared_repos_base: Optional[Path] = None) -> bool:
        """拉取最新代码（使用 GitPython，支持共享仓库和 worktree）

        工作流程：
        1. 检查是否有共享仓库（/mnt/oss/repos/{repo_hash}/）
        2. 如果有，使用 git worktree 创建工作副本到 workspace_path
        3. 如果没有，先克隆共享仓库，再创建工作副本
        4. 更新共享仓库（fetch）
        5. 在工作副本中切换到指定分支

        优势：
        - 复用 Git 对象和历史记录（减少网络传输）
        - 多个任务操作同一仓库时，只需拉取一次代码
        - 每个任务独立工作，互不干扰

        Args:
            repo_url: 仓库 URL
            branch: 分支名称
            token: GitHub token（可选，用于私有仓库）
            use_worktree: 是否使用 worktree（默认 True，如果 False 则直接克隆到工作目录）
            shared_repos_base: 共享仓库的基础路径（默认使用 workspace_path.parent.parent / "repos"）

        Returns:
            是否成功
        """
        if not GITPYTHON_AVAILABLE:
            logger.error("GitPython is not available")
            return False

        try:
            # 如果工作目录已经是 Git 仓库，直接更新（兼容旧逻辑）
            if self._repo_exists():
                logger.info(f"Workspace is already a git repository, updating...")
                return self._update_existing_repo(repo_url, branch, token)

            # 如果不使用 worktree，直接克隆到工作目录（简单模式）
            if not use_worktree:
                logger.info(f"Not using worktree, cloning directly to {self.workspace_path}")
                return self._clone_directly(repo_url, branch, token)

            # 使用 worktree 模式：共享仓库 + 工作副本
            shared_repo_path = self._get_shared_repo_path(repo_url, shared_repos_base)
            logger.info(f"Using worktree mode: shared repo at {shared_repo_path}, worktree at {self.workspace_path}")

            # 1. 确保共享仓库存在
            if not self._ensure_shared_repo(shared_repo_path, repo_url, branch, token):
                logger.error("Failed to ensure shared repository")
                return False

            # 2. 使用 worktree 创建工作副本
            if not self._create_worktree(shared_repo_path, branch):
                logger.error("Failed to create worktree")
                return False

            # 3. 初始化工作副本的 Repo 对象
            if not self._ensure_repo():
                logger.error("Failed to initialize worktree repository")
                return False

            # 4. 配置用户信息
            self.configure_user()

            logger.info(f"Successfully set up worktree from shared repository (branch: {branch})")
            return True

        except GitError as e:
            logger.error(f"Git error pulling latest code: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error pulling latest code: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False

    def stage_files(self, files: List[str]) -> bool:
        """暂存文件（过滤被忽略的文件）

        参考主项目 GitManager._stage 实现
        """
        if not self._ensure_repo():
            return False

        try:
            tracked = self._filter_tracked_paths(files)
            if not tracked:
                logger.debug("All files are ignored; skipping staging")
                return False

            # 使用 GitPython 的 index.add 方法
            # 注意：GitPython 的 add 方法接受文件路径列表
            self.repo.index.add(tracked)
            logger.debug(f"Staged {len(tracked)} files (skipped {len(files) - len(tracked)} ignored)")
            return True
        except GitError as e:
            logger.error(f"Failed to stage files: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error staging files: {e}")
            return False

    def commit_changes(self, message: str) -> Optional[str]:
        """提交更改

        参考主项目 GitManager._commit_if_needed 实现

        Returns:
            提交 SHA，如果没有更改则返回 None
        """
        if not self._ensure_repo():
            return None

        if not self._has_pending_changes():
            logger.debug("No pending changes to commit")
            return None

        try:
            # 使用 GitPython 的 index.commit 方法
            commit = self.repo.index.commit(message)
            commit_sha = commit.hexsha
            logger.info(f"Committed changes: {commit_sha[:8]} - {message[:50]}")
            return commit_sha
        except GitError as e:
            logger.error(f"Failed to commit changes: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error committing changes: {e}")
            raise

    def push_branch(self, branch: str, remote: str = "origin", token: Optional[str] = None) -> bool:
        """推送分支到远程

        参考主项目 GitManager.push_all 的错误处理逻辑

        Args:
            branch: 分支名称
            remote: 远程名称
            token: GitHub token（可选）

        Returns:
            是否成功
        """
        if not self._ensure_repo():
            return False

        if not self._has_remote(remote):
            logger.warning(f"No remote '{remote}' configured; skipping push")
            return False

        try:
            # 如果使用 token，更新远程 URL
            if token:
                origin = self.repo.remotes[remote]
                current_url = origin.url
                if token not in current_url:
                    remote_url = self._embed_token_in_url(current_url, token)
                    origin.set_url(remote_url)
                    logger.debug(f"Updated remote URL with token")

            # 使用 GitPython 的 push 方法
            origin = self.repo.remotes[remote]
            push_info = origin.push(f"{branch}:{branch}", progress=GitProgress())

            # 检查推送结果
            for info in push_info:
                if info.flags & info.ERROR:
                    logger.error(f"Push error: {info.summary}")
                    return False
                elif info.flags & info.REJECTED:
                    logger.warning(f"Push rejected: {info.summary}")
                    return False

            logger.info(f"Successfully pushed branch {branch} to {remote}")
            return True
        except GitError as e:
            message = str(e)
            if "Repository not found" in message or "Could not read from remote repository" in message:
                logger.warning(
                    f"Push failed: remote repository is unavailable or access is denied. "
                    f"Error: {message}"
                )
            else:
                logger.error(f"Failed to push branch {branch}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error pushing branch {branch}: {e}")
            raise

    def create_feature_branch(self, branch_name: str, from_branch: str = "main") -> bool:
        """创建功能分支"""
        if not self._ensure_repo():
            return False

        try:
            # 如果分支已存在，先删除
            if self._branch_exists(branch_name):
                self.repo.git.branch("-D", branch_name)

            # 切换到源分支
            self.repo.git.checkout(from_branch)

            # 创建新分支
            self.repo.git.checkout("-b", branch_name)

            logger.info(f"Created feature branch: {branch_name}")
            return True
        except GitError as e:
            logger.error(f"Failed to create feature branch {branch_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating feature branch {branch_name}: {e}")
            return False

    def _get_repo_hash(self, repo_url: str) -> str:
        """生成仓库的唯一哈希（用于共享仓库路径）"""
        import hashlib
        # 移除可能的 token 和协议差异，生成一致的哈希
        normalized_url = repo_url
        if "@" in normalized_url:
            # 移除 token
            normalized_url = re.sub(r'://[^@]+@', '://', normalized_url)
        normalized_url = normalized_url.replace("git@", "").replace("https://", "").replace("http://", "").replace(".git", "")
        hash_obj = hashlib.md5(normalized_url.encode())
        return hash_obj.hexdigest()[:16]

    def _get_shared_repo_path(self, repo_url: str, base_path: Optional[Path] = None) -> Path:
        """获取共享仓库路径"""
        if base_path is None:
            # 默认使用工作目录的父目录的 repos 子目录
            base_path = self.workspace_path.parent.parent / "repos"
        else:
            base_path = Path(base_path)

        repo_hash = self._get_repo_hash(repo_url)
        return base_path / repo_hash

    def _clone_directly(self, repo_url: str, branch: str, token: Optional[str] = None) -> bool:
        """直接克隆到工作目录（不使用 worktree）"""
        # 如果目录已存在，清理它
        if self.workspace_path.exists():
            shutil.rmtree(self.workspace_path)
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        # 克隆仓库（支持 HTTPS URL 带 token）
        clone_url = self._embed_token_in_url(repo_url, token)

        try:
            # 尝试克隆指定分支
            self.repo = Repo.clone_from(
                clone_url,
                str(self.workspace_path),
                branch=branch,
                depth=1,
                progress=GitProgress()
            )
            logger.info(f"Successfully cloned repository from {repo_url} (branch: {branch})")
        except GitError as e:
            # 如果指定分支失败，尝试克隆默认分支
            logger.warning(f"Failed to clone with branch {branch}, trying default branch: {e}")
            try:
                self.repo = Repo.clone_from(
                    clone_url,
                    str(self.workspace_path),
                    depth=1,
                    progress=GitProgress()
                )
                # 检查远程分支是否存在，如果存在则切换
                try:
                    remote_branches = self.repo.git.ls_remote("--heads", "origin", branch)
                    if remote_branches.strip():
                        self.repo.git.checkout("-b", branch, f"origin/{branch}")
                        logger.info(f"Switched to branch {branch} after cloning default branch")
                    else:
                        logger.warning(f"Branch {branch} not found, staying on default branch")
                except Exception:
                    logger.warning(f"Branch {branch} not found, staying on default branch")
            except Exception as e2:
                logger.error(f"Failed to clone repository: {e2}")
                return False

        # 配置用户信息
        self.configure_user()
        return True

    def _ensure_shared_repo(self, shared_repo_path: Path, repo_url: str, branch: str, token: Optional[str] = None) -> bool:
        """确保共享仓库存在并更新"""
        shared_repo: Optional[Repo] = None

        # 检查共享仓库是否存在
        if (shared_repo_path / ".git").exists():
            try:
                shared_repo = Repo(str(shared_repo_path))
                logger.info(f"Shared repository exists at {shared_repo_path}")
            except Exception as e:
                logger.warning(f"Shared repository exists but is invalid: {e}, re-cloning...")
                shutil.rmtree(shared_repo_path)
                shared_repo = None

        # 如果共享仓库不存在，克隆它
        if shared_repo is None:
            logger.info(f"Cloning shared repository from {repo_url} to {shared_repo_path}")
            shared_repo_path.parent.mkdir(parents=True, exist_ok=True)

            # 如果目录已存在但损坏，清理它
            if shared_repo_path.exists():
                shutil.rmtree(shared_repo_path)

            clone_url = self._embed_token_in_url(repo_url, token)

            try:
                shared_repo = Repo.clone_from(
                    clone_url,
                    str(shared_repo_path),
                    depth=1,
                    progress=GitProgress()
                )
                logger.info(f"Successfully cloned shared repository")
            except Exception as e:
                logger.error(f"Failed to clone shared repository: {e}")
                return False

        # 配置用户信息
        try:
            with shared_repo.config_writer() as cw:
                cw.set_value("user", "name", "Sleepless Agent")
                cw.set_value("user", "email", "agent@sleepless.local")
        except Exception as e:
            logger.warning(f"Failed to configure git user in shared repo: {e}")

        # 更新共享仓库（fetch）
        try:
            if not shared_repo.remotes:
                remote_url = self._embed_token_in_url(repo_url, token)
                shared_repo.create_remote("origin", remote_url)
                logger.info(f"Added remote origin to shared repository")
            else:
                # 更新远程 URL（如果需要）
                origin = shared_repo.remotes.origin
                # 更新远程 URL（如果需要）
                current_url = origin.url
                normalized_current = current_url.replace(f"{token}@", "") if token and token in current_url else current_url
                normalized_repo = repo_url.replace(f"{token}@", "") if token and token in repo_url else repo_url
                if normalized_current != normalized_repo:
                    remote_url = self._embed_token_in_url(repo_url, token)
                    origin.set_url(remote_url)
                    logger.info(f"Updated remote origin in shared repository")

            # 拉取最新代码
            origin = shared_repo.remotes.origin
            origin.fetch(progress=GitProgress())
            logger.info(f"Updated shared repository from remote")
        except Exception as e:
            logger.warning(f"Failed to update shared repository: {e}, continuing...")

        return True

    def _create_worktree(self, shared_repo_path: Path, branch: str) -> bool:
        """使用 git worktree 创建工作副本"""
        shared_repo = Repo(str(shared_repo_path))

        # 如果工作目录已存在，清理它
        if self.workspace_path.exists():
            # 检查是否是已有的 worktree
            try:
                worktrees = shared_repo.git.worktree("list")
                for line in worktrees.split('\n'):
                    if str(self.workspace_path) in line:
                        # 移除已有的 worktree
                        logger.info(f"Removing existing worktree at {self.workspace_path}")
                        shared_repo.git.worktree("remove", str(self.workspace_path), force=True)
                        break
            except Exception as e:
                logger.warning(f"Failed to check existing worktrees: {e}")

            # 清理目录
            shutil.rmtree(self.workspace_path)

        self.workspace_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查远程分支是否存在
        try:
            remote_branches = shared_repo.git.ls_remote("--heads", "origin", branch)
            if remote_branches.strip():
                # 远程分支存在，创建 worktree 跟踪远程分支
                try:
                    shared_repo.git.worktree("add", "-b", branch, str(self.workspace_path), f"origin/{branch}")
                    logger.info(f"Created worktree tracking origin/{branch}")
                except Exception as e:
                    # 如果创建失败，尝试使用现有分支
                    logger.warning(f"Failed to create worktree with new branch: {e}, trying existing branch")
                    shared_repo.git.worktree("add", str(self.workspace_path), branch)
            else:
                # 远程分支不存在，创建本地分支的 worktree
                shared_repo.git.worktree("add", "-b", branch, str(self.workspace_path))
                logger.info(f"Created worktree with new local branch {branch}")
        except Exception as e:
            logger.warning(f"Failed to create worktree with branch {branch}: {e}, trying default branch")
            # 如果失败，尝试使用默认分支
            try:
                shared_repo.git.worktree("add", str(self.workspace_path))
                # 然后切换到指定分支
                worktree_repo = Repo(str(self.workspace_path))
                worktree_repo.git.checkout("-b", branch)
                logger.info(f"Created worktree and switched to branch {branch}")
            except Exception as e2:
                logger.error(f"Failed to create worktree: {e2}")
                return False

        return True

    def _update_existing_repo(self, repo_url: str, branch: str, token: Optional[str] = None) -> bool:
        """更新已存在的 Git 仓库"""
        if not self._ensure_repo():
            logger.error("Failed to initialize Git repository")
            return False

        # 配置用户信息
        self.configure_user()

        # 如果没有远程仓库，添加
        if not self._has_remote():
            remote_url = self._embed_token_in_url(repo_url, token)
            self.repo.create_remote("origin", remote_url)
            logger.info(f"Added remote origin: {remote_url}")
        else:
            # 更新远程 URL（如果需要）
            origin = self.repo.remotes.origin
            current_url = origin.url
            # 规范化 URL 比较（移除 token）
            normalized_current = current_url.replace(f"{token}@", "") if token and token in current_url else current_url
            normalized_repo = repo_url.replace(f"{token}@", "") if token and token in repo_url else repo_url
            if normalized_current != normalized_repo:
                remote_url = self._embed_token_in_url(repo_url, token)
                origin.set_url(remote_url)
                logger.info(f"Updated remote origin: {remote_url}")

        # 拉取最新代码
        origin = self.repo.remotes.origin
        origin.fetch(progress=GitProgress())

        # 检查远程分支是否存在
        try:
            remote_branches = self.repo.git.ls_remote("--heads", "origin", branch)
            if remote_branches.strip():
                # 远程分支存在，切换到该分支
                if not self._branch_exists(branch):
                    self.repo.git.checkout("-b", branch, f"origin/{branch}")
                    logger.info(f"Created local branch {branch} tracking origin/{branch}")
                else:
                    self.repo.git.checkout(branch)
                    self.repo.git.reset("--hard", f"origin/{branch}")
                    logger.info(f"Reset branch {branch} to origin/{branch}")
            else:
                # 远程分支不存在，创建本地分支
                if not self._branch_exists(branch):
                    self.repo.git.checkout("-b", branch)
                    logger.info(f"Created local branch {branch} (remote branch not found)")
                else:
                    self.repo.git.checkout(branch)
                    logger.info(f"Switched to existing local branch {branch}")
        except Exception as e:
            logger.warning(f"Failed to check remote branches: {e}")
            # 如果检查失败，尝试直接切换分支
            if not self._branch_exists(branch):
                self.repo.git.checkout("-b", branch)
            else:
                self.repo.git.checkout(branch)

        logger.info(f"Successfully updated repository (branch: {branch})")
        return True

    def _embed_token_in_url(self, url: str, token: Optional[str]) -> str:
        """在 URL 中嵌入 token（用于私有仓库）"""
        if not token or "@" in url:
            return url

        if "github.com" in url:
            if url.startswith("https://"):
                return url.replace("https://", f"https://{token}@")
            elif url.startswith("http://"):
                return url.replace("http://", f"http://{token}@")

        return url

    def _run_git_safe(self, *args: str, timeout: int = 60) -> Tuple[bool, str]:
        """安全执行 Git 命令，不抛出异常（用于兼容性）

        注意：使用 GitPython 时，优先使用 GitPython 的方法
        此方法保留用于需要直接调用 git 命令的场景

        Returns:
            Tuple[success, output]
        """
        if not self._ensure_repo():
            return False, "Repository not initialized"

        try:
            # 使用 GitPython 的 git.execute 方法
            # with_extended_output=True 返回 (exit_code, stdout, stderr)
            # 注意：GitPython 的 execute 方法接受列表参数
            result = self.repo.git.execute(list(args), with_extended_output=True)
            exit_code, stdout, stderr = result
            if exit_code == 0:
                return True, stdout
            else:
                logger.debug(f"Git command failed (safe mode): {' '.join(args)} - {stderr}")
                return False, stderr
        except GitError as e:
            logger.debug(f"Git command failed (safe mode): {' '.join(args)} - {e}")
            return False, str(e)
        except Exception as e:
            logger.warning(f"Unexpected error in git command (safe mode): {' '.join(args)} - {e}")
            return False, str(e)


def extract_github_repo_info(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """从 GitHub URL 提取 owner 和 repo

    Args:
        repo_url: GitHub 仓库 URL

    Returns:
        Tuple[owner, repo]
    """
    match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$', repo_url)
    if not match:
        return None, None

    owner = match.group(1)
    repo = match.group(2).replace('.git', '')
    return owner, repo