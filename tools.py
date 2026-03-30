import base64
import os
import re

import httpx
from langchain_core.tools import tool


def _parse_repo_url(repo_url: str) -> tuple[str, str, str]:
    """Returns (host, owner, repo). Raises ValueError on invalid URL."""
    match = re.match(r"https?://([^/]+)/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url)
    if not match:
        raise ValueError(f"Invalid repo URL: {repo_url}")
    return match.groups()


def _github_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


@tool
def review_pr(pr_url: str) -> str:
    """Fetches the diff of a GitHub Pull Request.

    Use this tool when the user asks to review a PR or wants feedback on changed code.
    Input: pr_url — full URL of the pull request.
    Example: pr_url='https://alm-github.my-company.com/my-project/my-repo/pull/1'
    """
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        return "GITHUB_TOKEN is not set."

    # Parse: https://{host}/{owner}/{repo}/pull/{number}
    match = re.match(r"https?://([^/]+)/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        return f"Invalid PR URL format: {pr_url}"

    host, owner, repo, pr_number = match.groups()
    api_base = f"https://{host}/api/v3"
    headers = _github_headers(github_token)

    with httpx.Client(verify=False) as client:
        # Fetch PR metadata
        pr_resp = client.get(f"{api_base}/repos/{owner}/{repo}/pulls/{pr_number}", headers=headers)
        if pr_resp.status_code != 200:
            return f"Failed to fetch PR: HTTP {pr_resp.status_code} - {pr_resp.text}"
        pr_info = pr_resp.json()

        # Fetch changed files with patch (diff)
        files_resp = client.get(
            f"{api_base}/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=headers,
            params={"per_page": 100},
        )
        if files_resp.status_code != 200:
            return f"Failed to fetch PR files: HTTP {files_resp.status_code} - {files_resp.text}"
        files = files_resp.json()

    repo_url = f"https://{host}/{owner}/{repo}"
    head_ref = pr_info.get("head", {}).get("ref", "")
    base_ref = pr_info.get("base", {}).get("ref", "")

    lines = [
        f"PR #{pr_number}: {pr_info.get('title', '')}",
        f"Author: {pr_info.get('user', {}).get('login', '')}",
        f"Base: {base_ref}  ←  Head: {head_ref}",
        f"Repo URL: {repo_url}",
        f"Files changed: {len(files)}",
        f"Description: {pr_info.get('body', '').strip() or '(none)'}",
        "",
    ]

    for f in files:
        lines.append(f"### {f['filename']} ({f['status']}, +{f['additions']} -{f['deletions']})")
        patch = f.get("patch", "")
        if patch:
            lines.append(patch)
        else:
            lines.append("(binary or no diff available)")
        lines.append("")

    return "\n".join(lines)


@tool
def search_code_symbol(symbol: str, repo_url: str) -> str:
    """Search for a function, class, or variable definition in a GitHub repository.

    Use this tool when reviewing a PR and you need to understand what a called
    function or class does. It finds where the symbol is defined in the codebase.

    symbol: the function, class, or variable name to search for.
    repo_url: e.g. 'https://alm-github.my-company.com/org/repo'
    """
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        return "GITHUB_TOKEN is not set."
    try:
        host, owner, repo = _parse_repo_url(repo_url)
    except ValueError as e:
        return str(e)

    headers = _github_headers(github_token)
    with httpx.Client(verify=False) as client:
        resp = client.get(
            f"https://{host}/api/v3/search/code",
            headers=headers,
            params={"q": f"{symbol} repo:{owner}/{repo}"},
        )
        if resp.status_code != 200:
            return f"Search failed: HTTP {resp.status_code} - {resp.text}"
        items = resp.json().get("items", [])

        if not items:
            return f"No results found for '{symbol}' in {owner}/{repo}."

        results = [f"Found '{symbol}' in {len(items)} file(s):"]
        for item in items[:5]:
            path = item["path"]
            results.append(f"\n### {path}")
            # Fetch a snippet around the symbol
            content_resp = client.get(
                f"https://{host}/api/v3/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
            )
            if content_resp.status_code == 200:
                raw = base64.b64decode(content_resp.json()["content"]).decode("utf-8", errors="replace")
                lines_all = raw.splitlines()
                # Find first line containing the symbol and return ±5 lines of context
                for i, line in enumerate(lines_all):
                    if symbol in line:
                        start = max(0, i - 5)
                        end = min(len(lines_all), i + 6)
                        snippet = "\n".join(f"{start + j + 1}: {l}" for j, l in enumerate(lines_all[start:end]))
                        results.append(f"```\n{snippet}\n```")
                        break
            else:
                results.append("(could not fetch snippet)")
    return "\n".join(results)


@tool
def get_file_content(file_path: str, repo_url: str, ref: str = None) -> str:
    """Get the full content of a file from a GitHub repository.

    Use this tool when reviewing a PR and you need the full context of a file,
    for example to read a function definition found via search_code_symbol.

    file_path: relative path in the repo, e.g. 'src/utils/helper.py'
    repo_url: e.g. 'https://alm-github.my-company.com/org/repo'
    ref: branch or commit SHA (default: repo default branch).
         When reviewing a PR, pass the PR head branch ref to see the current state of the code.
         Only pass the base branch ref if you need to compare against the pre-change version.
         The head and base branch names are available in the output of review_pr.
    """
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        return "GITHUB_TOKEN is not set."
    try:
        host, owner, repo = _parse_repo_url(repo_url)
    except ValueError as e:
        return str(e)

    headers = _github_headers(github_token)
    params = {"ref": ref} if ref else {}
    with httpx.Client(verify=False) as client:
        resp = client.get(
            f"https://{host}/api/v3/repos/{owner}/{repo}/contents/{file_path}",
            headers=headers,
            params=params,
        )
        if resp.status_code != 200:
            return f"Failed to get file: HTTP {resp.status_code} - {resp.text}"
        data = resp.json()

    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    lines = content.splitlines()
    if len(lines) > 200:
        content = "\n".join(lines[:200]) + f"\n\n... (truncated, {len(lines)} lines total)"
    return content


@tool
def get_weather(location: str):
    """查询指定城市的天气。

    示例: `location='北京'` 或 `location='bj'`。
    """
    if not location:
        return "请提供要查询的城市，例如: '北京'。"

    loc = location.lower()
    if "北京" in location or "bj" in loc:
        return "北京天气晴，25℃"

    return f"{location}目前多云，20℃"
