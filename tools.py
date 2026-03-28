import os
import re

import httpx
from langchain_core.tools import tool

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

    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}

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

    lines = [
        f"PR #{pr_number}: {pr_info.get('title', '')}",
        f"Author: {pr_info.get('user', {}).get('login', '')}",
        f"Base: {pr_info.get('base', {}).get('ref', '')}  ←  Head: {pr_info.get('head', {}).get('ref', '')}",
        f"Files changed: {len(files)}",
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