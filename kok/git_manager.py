"""
Git Manager — module for working with git in Tayfa Orchestrator.

Contains all git operations: status, commit, push, branch, release, etc.
Uses subprocess to execute git commands.
"""

import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

# Setup paths for module imports
KOK_DIR = Path(__file__).resolve().parent
TEMPLATE_COMMON_DIR = KOK_DIR / "template_tayfa" / "common"
if str(TEMPLATE_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_COMMON_DIR))
if str(KOK_DIR) not in sys.path:
    sys.path.insert(0, str(KOK_DIR))

from settings_manager import (
    load_settings, get_next_version, save_version,
)
from task_manager import get_sprint, update_sprint_release
from project_manager import get_project_dir, get_project_repo_name

# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/git", tags=["git"])


# ── Helper Functions ──────────────────────────────────────────────────────────

def _to_wsl_path(path: Path | str) -> str:
    """
    Converts a Windows path to a WSL path for use with subprocess.

    C:\\Users\\... -> /mnt/c/Users/...
    /mnt/c/Users/... -> /mnt/c/Users/... (no changes)
    """
    path_str = str(path).strip()

    # Already a WSL path
    if path_str.startswith("/mnt/"):
        return path_str

    # Windows path: C:\Users\... or C:/Users/...
    if len(path_str) >= 2 and path_str[1] == ':':
        drive = path_str[0].lower()
        rest = path_str[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"

    # Other paths (relative, Unix) — leave as is
    return path_str


def _get_git_env() -> dict:
    """
    Returns environment variables for Git with user.name and user.email from settings.
    """
    import os
    env = os.environ.copy()
    settings = load_settings()
    git_settings = settings.get("git", {})

    user_name = git_settings.get("userName", "").strip()
    user_email = git_settings.get("userEmail", "").strip()

    if user_name:
        env["GIT_AUTHOR_NAME"] = user_name
        env["GIT_COMMITTER_NAME"] = user_name
    if user_email:
        env["GIT_AUTHOR_EMAIL"] = user_email
        env["GIT_COMMITTER_EMAIL"] = user_email

    return env


def _get_git_settings() -> dict:
    """Returns Git settings from settings.json."""
    settings = load_settings()
    return settings.get("git", {})


def _get_authenticated_remote_url(remote_url: str) -> str:
    """
    Returns URL with token for GitHub authentication.
    Format: https://TOKEN@github.com/user/repo.git
    """
    git_settings = _get_git_settings()
    token = git_settings.get("githubToken", "").strip()

    if not token or not remote_url:
        return remote_url

    # Only HTTPS URLs are supported
    if remote_url.startswith("https://github.com/"):
        # https://github.com/user/repo.git -> https://TOKEN@github.com/user/repo.git
        return remote_url.replace("https://github.com/", f"https://{token}@github.com/")
    elif remote_url.startswith("https://") and "github.com" in remote_url:
        # May already have a token, replace it
        return re.sub(r"https://[^@]*@github\.com/", f"https://{token}@github.com/", remote_url)

    return remote_url


def _get_computed_remote_url() -> str:
    """
    Computes the remote URL from global githubOwner + per-project repoName.
    Returns e.g. 'https://github.com/owner/repo.git' or '' if missing.
    """
    git_settings = _get_git_settings()
    owner = git_settings.get("githubOwner", "").strip()
    repo_name = get_project_repo_name()

    if not owner or not repo_name:
        return ""

    return f"https://github.com/{owner}/{repo_name}.git"


def _ensure_github_repo_exists(owner: str, repo_name: str, token: str) -> dict:
    """
    Checks if a GitHub repo exists; creates it if not.
    Uses urllib to avoid extra dependencies.

    Returns: {"existed": bool, "created": bool, "error": str|None}
    """
    import json as _json
    import urllib.request
    import urllib.error

    result = {"existed": False, "created": False, "error": None}

    # Check if repo exists
    check_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    req = urllib.request.Request(check_url, method="GET")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "Tayfa-Orchestrator")

    try:
        urllib.request.urlopen(req, timeout=10)
        result["existed"] = True
        return result
    except urllib.error.HTTPError as e:
        if e.code != 404:
            result["error"] = f"GitHub API error checking repo: {e.code} {e.reason}"
            return result
        # 404 = repo doesn't exist, proceed to create
    except Exception as e:
        result["error"] = f"GitHub API request failed: {str(e)}"
        return result

    # Create repo — try user repo first
    create_url = "https://api.github.com/user/repos"
    body = _json.dumps({
        "name": repo_name,
        "private": False,
        "auto_init": False,
    }).encode("utf-8")

    req = urllib.request.Request(create_url, data=body, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Tayfa-Orchestrator")

    try:
        urllib.request.urlopen(req, timeout=15)
        result["created"] = True
        return result
    except urllib.error.HTTPError as e:
        # If 422 (repo already exists — race condition), treat as existed
        if e.code == 422:
            result["existed"] = True
            return result
        # If forbidden, the owner might be an org — try org endpoint
        if e.code == 404 or e.code == 403:
            pass  # fall through to org attempt
        else:
            result["error"] = f"GitHub API error creating repo: {e.code} {e.reason}"
            return result
    except Exception as e:
        result["error"] = f"GitHub API create request failed: {str(e)}"
        return result

    # Try org endpoint
    org_url = f"https://api.github.com/orgs/{owner}/repos"
    req = urllib.request.Request(org_url, data=body, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Tayfa-Orchestrator")

    try:
        urllib.request.urlopen(req, timeout=15)
        result["created"] = True
        return result
    except urllib.error.HTTPError as e:
        if e.code == 422:
            result["existed"] = True
            return result
        result["error"] = f"GitHub API error creating org repo: {e.code} {e.reason}"
        return result
    except Exception as e:
        result["error"] = f"GitHub API org create request failed: {str(e)}"
        return result


def run_git_command(args: list[str], cwd: Path | None = None, use_config: bool = True) -> dict:
    """
    Executes a git command via subprocess.
    Returns {"success": bool, "stdout": str, "stderr": str}.
    By default cwd = get_project_dir() (project root).
    use_config: apply user.name/user.email from application settings.
    """
    if cwd is None:
        cwd = get_project_dir()
        if cwd is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "No project selected. Open a project via /api/projects/open",
            }

    try:
        env = _get_git_env() if use_config else None
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Git command execution timeout"}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "git not found on the system"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def _setup_git_remote() -> dict:
    """
    Configures git remote origin from computed URL (githubOwner + repoName).
    Falls back to legacy remoteUrl from settings if computed URL is empty.
    Returns {"success": bool, "message": str}.
    """
    # Try computed URL first (new approach)
    remote_url = _get_computed_remote_url()

    # Fallback to legacy remoteUrl if computed URL is empty
    if not remote_url:
        git_settings = _get_git_settings()
        remote_url = git_settings.get("remoteUrl", "").strip()

    if not remote_url:
        return {"success": False, "message": "Remote URL is not configured. Set GitHub Owner in settings and Repo Name for the project."}

    # Get URL with token
    auth_url = _get_authenticated_remote_url(remote_url)

    # Check if origin already exists
    check = run_git_command(["remote", "get-url", "origin"], use_config=False)
    if check["success"]:
        # Origin exists, update URL
        result = run_git_command(["remote", "set-url", "origin", auth_url], use_config=False)
    else:
        # Add new remote
        result = run_git_command(["remote", "add", "origin", auth_url], use_config=False)

    if result["success"]:
        return {"success": True, "message": "Remote origin configured"}
    else:
        return {"success": False, "message": result["stderr"]}


def _check_git_initialized() -> dict | None:
    """Checks if git is initialized. Returns an error or None."""
    project_dir = get_project_dir()
    if project_dir is None:
        return {"error": "No project selected"}
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {"error": "Git not initialized"}
    return None


def check_git_state() -> dict:
    """
    Checks the git state for creating a sprint branch.

    Returns:
    {
        "initialized": bool,
        "has_remote": bool,
        "main_branch": str | None,  # "main" or "master" or None
        "error": str | None,  # Critical error
        "warning": str | None  # Warning (non-blocking)
    }
    """
    result = {
        "initialized": False,
        "has_remote": False,
        "main_branch": None,
        "error": None,
        "warning": None,
    }

    project_dir = get_project_dir()
    if project_dir is None:
        result["error"] = "No project selected. Open a project via the interface"
        return result

    # Check 1: is git initialized?
    git_check = run_git_command(["rev-parse", "--git-dir"])
    if not git_check["success"]:
        result["error"] = "Git is not initialized. Run git init or use the 'Initialize Git' button"
        return result
    result["initialized"] = True

    # Check 2: does remote origin exist?
    remote_check = run_git_command(["remote", "get-url", "origin"], use_config=False)
    if remote_check["success"]:
        result["has_remote"] = True
    else:
        result["warning"] = "Remote origin is not configured. Branch will be created locally"

    # Check 3: which main branch exists (main or master)?
    main_check = run_git_command(["show-ref", "--verify", "refs/heads/main"])
    if main_check["success"]:
        result["main_branch"] = "main"
    else:
        master_check = run_git_command(["show-ref", "--verify", "refs/heads/master"])
        if master_check["success"]:
            result["main_branch"] = "master"
        else:
            # Neither main nor master — check if there are any commits at all
            log_check = run_git_command(["log", "-1"])
            if not log_check["success"]:
                result["error"] = "No commits in the repository. Create the first commit before creating a sprint"
            else:
                # There are commits but no main/master — use the current branch
                branch_check = run_git_command(["branch", "--show-current"])
                if branch_check["success"] and branch_check["stdout"]:
                    result["main_branch"] = branch_check["stdout"]
                    result["warning"] = f"main/master branches not found, using current branch '{branch_check['stdout']}'"
                else:
                    result["error"] = "Failed to determine the base branch"

    return result


def check_branch_exists(branch_name: str) -> bool:
    """Checks if a local branch exists."""
    result = run_git_command(["show-ref", "--verify", f"refs/heads/{branch_name}"])
    return result["success"]


def create_sprint_branch(sprint_id: str) -> dict:
    """
    Creates a branch for the sprint from the main branch (main/master).

    Returns:
    {
        "success": bool,
        "branch": str | None,
        "git_status": "ok" | "warning" | "error",
        "git_warning": str | None,
        "error": str | None
    }
    """
    branch_name = f"sprint/{sprint_id}"
    result = {
        "success": False,
        "branch": None,
        "git_status": "error",
        "git_warning": None,
        "error": None,
    }

    # Check git state
    state = check_git_state()

    if state["error"]:
        result["error"] = state["error"]
        return result

    # Save warning (if any)
    if state["warning"]:
        result["git_warning"] = state["warning"]

    main_branch = state["main_branch"]

    # Check if the branch already exists
    if check_branch_exists(branch_name):
        result["error"] = f"Branch {branch_name} already exists"
        return result

    # Switch to main branch
    checkout_main = run_git_command(["checkout", main_branch])
    if not checkout_main["success"]:
        result["error"] = f"Failed to switch to {main_branch}: {checkout_main['stderr']}"
        return result

    # Pull if remote exists
    if state["has_remote"]:
        pull_result = run_git_command(["pull", "origin", main_branch])
        if not pull_result["success"]:
            # Pull failed — warn but continue
            if result["git_warning"]:
                result["git_warning"] += f"; Pull failed: {pull_result['stderr']}"
            else:
                result["git_warning"] = f"Failed to pull (possibly offline): {pull_result['stderr']}"

    # Create sprint branch
    create_branch = run_git_command(["checkout", "-b", branch_name])
    if not create_branch["success"]:
        result["error"] = f"Failed to create branch {branch_name}: {create_branch['stderr']}"
        return result

    # Success!
    result["success"] = True
    result["branch"] = branch_name
    result["git_status"] = "warning" if result["git_warning"] else "ok"

    return result


def commit_task(task_id: str, title: str) -> dict:
    """
    Commits all changes with the message 'T001: title'.

    Returns:
    {
        "success": bool,
        "commit": str | None,  # short hash
        "message": str | None,
        "error": str | None
    }
    """
    result = {
        "success": False,
        "commit": None,
        "message": None,
        "error": None,
    }

    commit_message = f"{task_id}: {title}"

    # git add -A
    add_result = run_git_command(["add", "-A"])
    if not add_result["success"]:
        result["error"] = f"git add error: {add_result['stderr']}"
        return result

    # git commit
    commit_result = run_git_command(["commit", "-m", commit_message])
    if not commit_result["success"]:
        # Check if there is anything to commit
        if "nothing to commit" in commit_result.get("stdout", "") + commit_result.get("stderr", ""):
            result["error"] = "Nothing to commit — no changes"
            return result
        result["error"] = f"git commit error: {commit_result['stderr']}"
        return result

    # Get commit hash
    hash_result = run_git_command(["rev-parse", "--short", "HEAD"])

    result["success"] = True
    result["commit"] = hash_result["stdout"] if hash_result["success"] else None
    result["message"] = commit_message

    return result


def release_sprint(sprint_id: str, version: str | None = None, skip_checks: bool = False) -> dict:
    """
    Performs a sprint release: merge sprint branch into main, create tag, push.

    Args:
        sprint_id: Sprint ID (e.g., "S001")
        version: Release version (optional, auto-increment if not specified)
        skip_checks: Skip git status checks (default False)

    Returns:
    {
        "success": bool,
        "version": str | None,
        "commit": str | None,
        "message": str | None,
        "tag_created": bool,
        "pushed": bool,
        "warnings": list | None,
        "error": str | None
    }
    """
    result = {
        "success": False,
        "version": None,
        "commit": None,
        "message": None,
        "tag_created": False,
        "pushed": False,
        "warnings": None,
        "error": None,
    }

    # Check git readiness for release
    if not skip_checks:
        git_check = check_git_ready_for_release()
        if not git_check["ready"]:
            result["error"] = "; ".join(git_check["errors"])
            return result
        if git_check.get("warnings"):
            result["warnings"] = git_check["warnings"]

    # Check git
    err = _check_git_initialized()
    if err:
        result["error"] = err["error"]
        return result

    # Get sprint information
    sprint = get_sprint(sprint_id)
    if not sprint:
        result["error"] = f"Sprint {sprint_id} not found"
        return result

    sprint_title = sprint.get("title", "")
    source_branch = f"sprint/{sprint_id}"
    target_branch = "main"

    # Determine version
    if not version:
        tag_result = run_git_command(["describe", "--tags", "--abbrev=0"])
        if tag_result["success"] and tag_result["stdout"]:
            version = get_next_version()
        else:
            version = "v0.1.0"

    result["version"] = version

    # Build message
    merge_message = f"Release {version}: {sprint_title}" if sprint_title else f"Release {version}"
    result["message"] = merge_message

    try:
        # 0. Configure remote
        _setup_git_remote()

        # 1. Switch to source_branch and update
        checkout_src = run_git_command(["checkout", source_branch])
        if not checkout_src["success"]:
            result["error"] = f"Branch {source_branch} not found: {checkout_src['stderr']}"
            return result
        run_git_command(["pull", "origin", source_branch])

        # 2. Switch to target_branch
        checkout_tgt = run_git_command(["checkout", target_branch])
        if not checkout_tgt["success"]:
            # Create main if it does not exist
            create_tgt = run_git_command(["checkout", "-b", target_branch])
            if not create_tgt["success"]:
                result["error"] = f"Failed to create branch {target_branch}: {create_tgt['stderr']}"
                run_git_command(["checkout", source_branch])
                return result
        else:
            run_git_command(["pull", "origin", target_branch])

        # 3. Merge
        merge_result = run_git_command(["merge", source_branch, "--no-ff", "-m", merge_message])
        if not merge_result["success"]:
            run_git_command(["merge", "--abort"])
            run_git_command(["checkout", source_branch])
            result["error"] = f"Merge conflict: {merge_result['stderr']}"
            return result

        # 4. Get hash
        hash_result = run_git_command(["rev-parse", "--short", "HEAD"])
        result["commit"] = hash_result["stdout"] if hash_result["success"] else None

        # 5. Create tag
        tag_msg = f"Sprint: {sprint_title}" if sprint_title else f"Release {version}"
        tag_result = run_git_command(["tag", "-a", version, "-m", tag_msg])
        result["tag_created"] = tag_result["success"]

        # 6. Push
        push_result = run_git_command(["push", "origin", target_branch, "--tags"])
        result["pushed"] = push_result["success"]

        if not result["pushed"]:
            # Retry: branch first, then tags
            push_branch = run_git_command(["push", "origin", target_branch])
            if push_branch["success"]:
                run_git_command(["push", "origin", "--tags"])
                result["pushed"] = True

        # 7. If push failed — roll back merge and tag
        if not result["pushed"]:
            # Delete local tag
            run_git_command(["tag", "-d", version])
            # Roll back merge (return main to the state before merge)
            run_git_command(["reset", "--hard", "HEAD~1"])
            # Return to sprint branch
            run_git_command(["checkout", source_branch])
            result["error"] = f"Push failed: {push_result.get('stderr', 'Unknown error')}. Merge and tag rolled back."
            return result

        # 8. Save version (only on successful push)
        save_version(version)

        # 9. Update sprint (only on successful push)
        update_sprint_release(sprint_id, version, pushed=result["pushed"])

        # 10. Return to source_branch
        run_git_command(["checkout", source_branch])

        result["success"] = True
        return result

    except Exception as e:
        run_git_command(["checkout", source_branch])
        result["error"] = str(e)
        return result


def _check_gh_cli() -> dict | None:
    """Checks if gh CLI is installed. Returns an error or None."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"error": "gh CLI not found"}
        return None
    except FileNotFoundError:
        return {"error": "gh CLI not found"}
    except Exception as e:
        return {"error": f"gh CLI check failed: {str(e)}"}


def check_git_ready_for_release() -> dict:
    """
    Checks git readiness for release operations (merge, push).

    Performs checks in the following order:
    1. Git is initialized (.git folder exists)
    2. Remote is configured (git remote get-url origin)
    3. No uncommitted changes (git status --porcelain)
    4. Remote is reachable (git ls-remote --exit-code origin)

    Returns:
        {
            "ready": bool,
            "errors": [],      # Blocking errors
            "warnings": [],    # Warnings (non-blocking)
            "details": {
                "branch": str,
                "remote": str,
                "remote_url": str
            }
        }
    """
    errors = []
    warnings = []
    details = {
        "branch": "",
        "remote": "origin",
        "remote_url": ""
    }

    project_dir = get_project_dir()
    if project_dir is None:
        return {
            "ready": False,
            "errors": ["No project selected. Open a project via settings"],
            "warnings": [],
            "details": details
        }

    # 1. Check: Git is initialized
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        errors.append("Git is not initialized. Run git init")
        return {
            "ready": False,
            "errors": errors,
            "warnings": warnings,
            "details": details
        }

    # Get current branch
    branch_res = run_git_command(["branch", "--show-current"])
    if branch_res["success"]:
        details["branch"] = branch_res["stdout"]

    # 2. Check: Remote is configured
    remote_res = run_git_command(["remote", "get-url", "origin"], use_config=False)
    if not remote_res["success"]:
        errors.append("Remote is not configured. Specify a GitHub repository in settings")
        return {
            "ready": False,
            "errors": errors,
            "warnings": warnings,
            "details": details
        }

    # Hide token in URL for security when displaying
    raw_url = remote_res["stdout"]
    if "@github.com" in raw_url:
        # Mask token: https://token@github.com/... -> https://***@github.com/...
        display_url = re.sub(r"https://[^@]+@", "https://***@", raw_url)
    else:
        display_url = raw_url
    details["remote_url"] = display_url

    # 3. Check: No uncommitted changes
    status_res = run_git_command(["status", "--porcelain"])
    if status_res["success"] and status_res["stdout"]:
        has_staged = False
        has_unstaged = False
        has_untracked = False

        for line in status_res["stdout"].split("\n"):
            if not line or len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]

            # Staged changes (in the index)
            if index_status in ("A", "M", "D", "R", "C"):
                has_staged = True
            # Unstaged changes (modified but not added)
            if worktree_status in ("M", "D"):
                has_unstaged = True
            # Untracked files (new files)
            if index_status == "?" and worktree_status == "?":
                has_untracked = True

        # Staged and unstaged — this is an error (blocking)
        if has_staged or has_unstaged:
            errors.append("There are uncommitted changes. Commit before releasing")

        # Untracked — this is a warning (non-blocking)
        if has_untracked and not has_staged and not has_unstaged:
            warnings.append("There are untracked files (new files not in git)")

    # If there are errors at this stage — do not check remote availability
    if errors:
        return {
            "ready": False,
            "errors": errors,
            "warnings": warnings,
            "details": details
        }

    # 4. Check: Remote is reachable (only if no other errors)
    # Before checking, update remote URL with the current token
    _setup_git_remote()

    # git ls-remote --exit-code checks availability and that remote is not empty
    # Using an increased timeout for network operations
    try:
        ls_remote_result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=15,  # 15 seconds for network operations
        )
        if ls_remote_result.returncode != 0:
            error_msg = ls_remote_result.stderr
            if "Authentication failed" in error_msg or "could not read" in error_msg:
                errors.append("No access to remote. Check your GitHub token and repository URL")
            elif "Could not resolve host" in error_msg:
                errors.append("Cannot connect to GitHub. Check your internet connection")
            elif "Repository not found" in error_msg:
                errors.append("Repository not found. Check the URL in settings")
            else:
                errors.append("No access to remote. Check your GitHub token and repository URL")
    except subprocess.TimeoutExpired:
        errors.append("GitHub connection timeout. Check your internet connection")
    except Exception as e:
        errors.append(f"Remote check error: {str(e)}")

    return {
        "ready": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "details": details
    }


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("/release-ready")
async def api_git_release_ready():
    """
    Check git readiness for release operations.

    Performs checks:
    1. Git is initialized
    2. Remote is configured
    3. No uncommitted changes
    4. Remote is reachable

    Returns:
    {
        "ready": true/false,
        "errors": ["error description"],
        "warnings": ["warning"],
        "details": {
            "branch": "sprint/S001",
            "remote": "origin",
            "remote_url": "https://github.com/..."
        }
    }
    """
    return check_git_ready_for_release()


@router.get("/status")
async def api_git_status():
    """
    Repository status.
    Returns: initialized, branch, staged, unstaged, untracked.
    If .git is absent, returns initialized=false (does not throw an error).
    """
    project_dir = get_project_dir()
    if project_dir is None:
        return {
            "initialized": False,
            "error": "no_project",
            "message": "No project selected"
        }

    # Check git initialization
    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return {
            "initialized": False,
            "error": "not_initialized",
            "message": "Git is not initialized"
        }

    result = {
        "initialized": True,
        "branch": "",
        "staged": [],
        "unstaged": [],
        "untracked": [],
    }

    # Current branch
    branch_res = run_git_command(["branch", "--show-current"])
    print(f"[DEBUG] git branch --show-current: {branch_res}")
    if branch_res["success"]:
        result["branch"] = branch_res["stdout"]

    # File status (porcelain for parsing)
    status_res = run_git_command(["status", "--porcelain"])
    if status_res["success"] and status_res["stdout"]:
        for line in status_res["stdout"].split("\n"):
            if not line or len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filename = line[3:]

            # Staged: files added to the index (A, M, D, R, C in the first position)
            if index_status in ("A", "M", "D", "R", "C"):
                result["staged"].append(filename)
            # Unstaged: modified but not added (M, D in the second position)
            if worktree_status in ("M", "D"):
                result["unstaged"].append(filename)
            # Untracked: new untracked files (??)
            if index_status == "?" and worktree_status == "?":
                result["untracked"].append(filename)

    return result


@router.get("/branches")
async def api_git_branches():
    """
    List of branches.
    Returns: current, branches (local + remotes/).
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    result = {
        "current": "",
        "branches": [],
    }

    # Current branch
    branch_res = run_git_command(["branch", "--show-current"])
    if branch_res["success"]:
        result["current"] = branch_res["stdout"]

    # All branches (local + remote)
    all_res = run_git_command(["branch", "-a", "--format=%(refname:short)"])
    if all_res["success"] and all_res["stdout"]:
        result["branches"] = [b.strip() for b in all_res["stdout"].split("\n") if b.strip()]

    return result


@router.post("/init")
async def api_git_init(data: dict = {}):
    """
    Initialize a git repository.
    Body (optional): {"create_initial_commit": true}
    """
    project_dir = get_project_dir()
    if project_dir is None:
        raise HTTPException(status_code=400, detail="No project selected. Open a project via /api/projects/open")

    git_dir = project_dir / ".git"
    if git_dir.exists():
        return {"success": True, "message": "Git repository already initialized", "initialized": True}

    # git init
    result = run_git_command(["init"])
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "git init error")

    response = {"success": True, "message": "Git repository initialized", "initialized": True}

    # Set default branch from settings
    default_branch = _get_git_settings().get("defaultBranch", "main")
    run_git_command(["config", "init.defaultBranch", default_branch], use_config=False)

    # Create .gitignore (always, if it does not exist)
    gitignore_path = project_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_content = """# Dependencies
node_modules/
__pycache__/
*.pyc
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Build
dist/
build/
*.egg-info/

# Environment
.env
.env.local
*.log

# OS
.DS_Store
Thumbs.db

# Tayfa internal
.tayfa/*/notes.md
"""
        try:
            gitignore_path.write_text(gitignore_content, encoding="utf-8")
            response["gitignore_created"] = True
        except Exception as e:
            response["gitignore_error"] = str(e)
            response["gitignore_created"] = False
    else:
        response["gitignore_created"] = False  # Already exists

    # Create initial commit (default true)
    create_initial_commit = data.get("create_initial_commit", True) if data else True
    if create_initial_commit:
        # Add .gitignore to staging
        add_result = run_git_command(["add", ".gitignore"], use_config=True)
        if add_result["success"]:
            # Create initial commit
            commit_result = run_git_command(["commit", "-m", "Initial commit"], use_config=True)
            if commit_result["success"]:
                response["initial_commit"] = True
                # Get the hash of the last commit
                hash_result = run_git_command(["rev-parse", "HEAD"], use_config=False)
                if hash_result["success"]:
                    response["commit_hash"] = hash_result["stdout"]
            else:
                # Not an error, but a warning
                response["initial_commit"] = False
                response["commit_warning"] = commit_result["stderr"] or "Failed to create initial commit"
        else:
            response["initial_commit"] = False
            response["commit_warning"] = f"Failed to add .gitignore: {add_result['stderr']}"
    else:
        response["initial_commit"] = False

    # Configure remote from settings (if specified)
    remote_result = _setup_git_remote()
    if remote_result["success"]:
        response["remote_configured"] = True
    elif _get_computed_remote_url() or _get_git_settings().get("remoteUrl"):
        response["remote_error"] = remote_result["message"]

    return response


@router.post("/setup-remote")
async def api_git_setup_remote():
    """
    Configures git remote origin from computed URL (githubOwner + repoName)
    or legacy remoteUrl. Uses githubToken for authentication.
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    result = _setup_git_remote()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return {"status": "configured", "message": result["message"]}


@router.get("/remote")
async def api_git_remote():
    """
    Get information about remote repositories.
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    result = run_git_command(["remote", "-v"], use_config=False)
    if not result["success"]:
        return {"remotes": []}

    remotes = []
    for line in result["stdout"].split("\n"):
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                # Hide token in URL for security
                url = parts[1]
                if "@github.com" in url:
                    url = url.split("@github.com")[0].rsplit("/", 1)[0] + "@github.com/***"
                remotes.append({"name": name, "url": url})

    return {"remotes": remotes}


@router.get("/diff")
async def api_git_diff(staged: bool = False, file: str | None = None):
    """
    View changes (diff).
    Parameters: ?staged=true — show staged changes, ?file=path — diff of a specific file
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    args = ["diff"]
    if staged:
        args.append("--staged")
    if file:
        args.append("--")
        args.append(file)

    result = run_git_command(args)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "git diff error")

    return {"diff": result["stdout"], "staged": staged, "file": file}


@router.post("/branch")
async def api_git_branch(data: dict):
    """
    Create a branch.
    Body: {"name": "feature/T025-git-api", "from_branch": "develop", "checkout": true}
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Field 'name' is required")

    from_branch = data.get("from_branch")
    checkout = data.get("checkout", True)

    if checkout:
        # git checkout -b <name> [from_branch]
        args = ["checkout", "-b", name]
        if from_branch:
            args.append(from_branch)
    else:
        # git branch <name> [from_branch]
        args = ["branch", name]
        if from_branch:
            args.append(from_branch)

    result = run_git_command(args)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "Branch creation error")

    return {
        "status": "created",
        "branch": name,
        "from_branch": from_branch,
        "checkout": checkout,
    }


@router.post("/commit")
async def api_git_commit(data: dict):
    """
    Create a commit.
    Body: {"message": "Commit message", "files": ["file1.py", "file2.js"]}
    If files is empty — git add -A is executed (adds all changes).
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    message = data.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Field 'message' is required")

    files = data.get("files", [])

    # Add files to the index
    if files:
        add_result = run_git_command(["add"] + files)
    else:
        # If files not specified — git add -A
        add_result = run_git_command(["add", "-A"])

    if not add_result["success"]:
        raise HTTPException(status_code=500, detail=add_result["stderr"] or "git add error")

    # Create commit
    commit_result = run_git_command(["commit", "-m", message])
    if not commit_result["success"]:
        # Check if there is anything to commit
        if "nothing to commit" in commit_result["stdout"] or "nothing to commit" in commit_result["stderr"]:
            raise HTTPException(status_code=400, detail="Nothing to commit — no changes in the index")
        raise HTTPException(status_code=500, detail=commit_result["stderr"] or "git commit error")

    # Get the hash of the new commit
    hash_result = run_git_command(["rev-parse", "--short", "HEAD"])
    commit_hash = hash_result["stdout"] if hash_result["success"] else ""

    # Count the number of committed files
    files_count = len(files) if files else "all"
    commit_message = f"Committed {files_count} files" if isinstance(files_count, int) else "Committed all staged files"

    return {
        "success": True,
        "hash": commit_hash,
        "message": commit_message,
    }


@router.post("/push")
async def api_git_push(data: dict):
    """
    Push to remote.
    Body: {"remote": "origin", "branch": null, "set_upstream": true, "skip_checks": false}

    Before push, a git status check is performed (can be disabled via skip_checks).
    """
    skip_checks = data.get("skip_checks", False)

    if not skip_checks:
        # Check git readiness for push
        git_check = check_git_ready_for_release()
        if not git_check["ready"]:
            # Build a clear error message
            error_details = "; ".join(git_check["errors"])
            raise HTTPException(status_code=400, detail=error_details)

    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    remote = data.get("remote", "origin")
    branch = data.get("branch")
    set_upstream = data.get("set_upstream", True)

    # Before push, update remote URL with the current token
    if remote == "origin":
        _setup_git_remote()

    # Auto-create GitHub repo if it doesn't exist
    repo_created = False
    repo_warning = None
    if remote == "origin":
        git_settings = _get_git_settings()
        token = git_settings.get("githubToken", "").strip()
        owner = git_settings.get("githubOwner", "").strip()
        repo_name = get_project_repo_name()

        if token and owner and repo_name:
            ensure_result = _ensure_github_repo_exists(owner, repo_name, token)
            if ensure_result.get("created"):
                repo_created = True
                # Re-setup remote after creation (in case it wasn't set)
                _setup_git_remote()
            elif ensure_result.get("error"):
                repo_warning = ensure_result["error"]
        elif not token:
            repo_warning = "GitHub token not configured — auto repo creation skipped."

    args = ["push"]
    if set_upstream:
        args.append("-u")
    args.append(remote)
    if branch:
        args.append(branch)

    result = run_git_command(args)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["stderr"] or "git push error")

    # Include warnings in the response (if any)
    response = {
        "status": "pushed",
        "remote": remote,
        "branch": branch,
        "set_upstream": set_upstream,
        "output": result["stdout"] or result["stderr"],
    }

    if repo_created:
        response["repo_created"] = True
    if repo_warning:
        response["repo_warning"] = repo_warning

    if not skip_checks:
        git_check = check_git_ready_for_release()
        if git_check.get("warnings"):
            response["warnings"] = git_check["warnings"]

    return response


@router.post("/pr")
async def api_git_pr(data: dict):
    """
    Create a Pull Request via gh CLI.
    Body: {"title": "T025: Git API", "body": "...", "base": "develop", "draft": false}
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    gh_err = _check_gh_cli()
    if gh_err:
        raise HTTPException(status_code=400, detail=gh_err["error"])

    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Field 'title' is required")

    body = data.get("body", "")
    base = data.get("base", "main")
    draft = data.get("draft", False)

    project_dir = get_project_dir()
    if project_dir is None:
        raise HTTPException(status_code=400, detail="No project selected")

    args = ["pr", "create", "--title", title, "--body", body, "--base", base]
    if draft:
        args.append("--draft")

    try:
        result = subprocess.run(
            ["gh"] + args,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr or "gh pr create error")

        # gh pr create outputs the URL of the created PR
        pr_url = result.stdout.strip()
        return {
            "status": "created",
            "title": title,
            "base": base,
            "draft": draft,
            "url": pr_url,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="gh pr create timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log")
async def api_git_log(limit: int = 20):
    """
    Commit history.
    Parameters: ?limit=20
    Returns: {"commits": [{"hash": "abc1234", "author": "Name", "date": "2026-02-11", "message": "..."}]}
    """
    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    # Format: short_hash|author|date_short|message
    # Using --date=short for YYYY-MM-DD format
    result = run_git_command([
        "log", f"-n{limit}",
        "--oneline",
        "--format=%h|%an|%ad|%s",
        "--date=short"
    ])

    if not result["success"]:
        # If there are no commits — return an empty list
        if "does not have any commits" in result["stderr"]:
            return {"commits": []}
        raise HTTPException(status_code=500, detail=result["stderr"] or "git log error")

    commits = []
    for line in result["stdout"].split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "date": parts[2],
                "message": parts[3],
            })

    return {"commits": commits}


@router.post("/release")
async def api_git_release(data: dict):
    """
    Create a release: merge develop -> main, create tag, push.

    Body: {
        "sprint_id": "S006",        // optional — to record version in sprint
        "version": "v0.2.0",        // optional — otherwise auto-increment
        "source_branch": "develop", // optional, default: develop
        "target_branch": "main",    // optional, default: main
        "skip_checks": false        // optional — skip checks
    }

    Before release, a git status check is performed:
    - Git is initialized
    - Remote is configured
    - No uncommitted changes
    - Remote is reachable

    Response (success): {
        "success": true,
        "version": "v0.2.0",
        "commit": "abc1234",
        "message": "Release v0.2.0: Sprint Title",
        "tag_created": true,
        "pushed": true
    }
    """
    skip_checks = data.get("skip_checks", False)

    # Check git readiness for release (if not skipped)
    if not skip_checks:
        git_check = check_git_ready_for_release()
        if not git_check["ready"]:
            # Build a clear error message
            error_details = "; ".join(git_check["errors"])
            raise HTTPException(status_code=400, detail=error_details)

    err = _check_git_initialized()
    if err:
        raise HTTPException(status_code=400, detail=err["error"])

    sprint_id = data.get("sprint_id")
    version = data.get("version")
    source_branch = data.get("source_branch", "develop")
    target_branch = data.get("target_branch", "main")

    # Get sprint information (if specified)
    sprint_title = ""
    if sprint_id:
        sprint = get_sprint(sprint_id)
        if sprint:
            sprint_title = sprint.get("title", "")

    # Determine version
    if not version:
        # Try to get the latest tag from git
        tag_result = run_git_command(["describe", "--tags", "--abbrev=0"])
        if tag_result["success"] and tag_result["stdout"]:
            # Tags exist — increment
            version = get_next_version()
        else:
            # No tags — start with v0.1.0
            version = "v0.1.0"

    # Build commit message
    if sprint_title:
        merge_message = f"Release {version}: {sprint_title}"
    else:
        merge_message = f"Release {version}"

    project_dir = get_project_dir()
    if project_dir is None:
        raise HTTPException(status_code=400, detail="No project selected")

    try:
        # 0. Configure remote with token for authentication
        _setup_git_remote()

        # 1. Make sure source_branch is up to date
        run_git_command(["checkout", source_branch])
        run_git_command(["pull", "origin", source_branch])

        # 2. Switch to target_branch and update
        checkout_result = run_git_command(["checkout", target_branch])
        if not checkout_result["success"]:
            # target_branch does not exist — create it
            create_result = run_git_command(["checkout", "-b", target_branch])
            if not create_result["success"]:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create branch {target_branch}: {create_result['stderr']}"
                )
        else:
            run_git_command(["pull", "origin", target_branch])

        # 3. Merge source → target
        merge_result = run_git_command([
            "merge", source_branch, "--no-ff", "-m", merge_message
        ])
        if not merge_result["success"]:
            # Conflict — roll back
            run_git_command(["merge", "--abort"])
            run_git_command(["checkout", source_branch])
            raise HTTPException(
                status_code=409,
                detail=f"Merge conflict: {merge_result['stderr']}"
            )

        # 4. Get commit hash
        hash_result = run_git_command(["rev-parse", "--short", "HEAD"])
        commit_hash = hash_result["stdout"] if hash_result["success"] else ""

        # 5. Create tag
        tag_message = f"Sprint: {sprint_title}" if sprint_title else f"Release {version}"
        tag_result = run_git_command(["tag", "-a", version, "-m", tag_message])
        tag_created = tag_result["success"]

        # 6. Push main and tags
        push_result = run_git_command(["push", "origin", target_branch, "--tags"])
        pushed = push_result["success"]

        if not pushed:
            # Try push without tags
            push_branch = run_git_command(["push", "origin", target_branch])
            if push_branch["success"]:
                # Push tags separately
                run_git_command(["push", "origin", "--tags"])
                pushed = True

        # 7. Save version in settings
        save_version(version)

        # 8. Update sprint (if specified) — using the public API
        if sprint_id:
            update_sprint_release(sprint_id, version, pushed=pushed)

        # 9. Return to source_branch
        run_git_command(["checkout", source_branch])

        return {
            "success": True,
            "version": version,
            "commit": commit_hash,
            "message": merge_message,
            "tag_created": tag_created,
            "pushed": pushed,
            "sprint_id": sprint_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Try to return to source_branch on error
        run_git_command(["checkout", source_branch])
        raise HTTPException(status_code=500, detail=str(e))
