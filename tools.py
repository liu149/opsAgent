import base64
import os
import re
from pathlib import Path

import httpx
from langchain_core.tools import tool

EXTENSION_TO_LANG = {
    ".py": "python",
    ".java": "java",
    ".go": "go",
    ".js": "javascript",
    ".ts": "typescript",
}


def _detect_language(file_path: str) -> str | None:
    return EXTENSION_TO_LANG.get(Path(file_path).suffix.lower())


def _extract_block_ast(source: str, symbol: str, lang: str) -> list[str] | None:
    """Extract a function/class/method body using tree-sitter AST. Returns None on failure."""
    try:
        from tree_sitter_languages import get_parser

        parser = get_parser(lang)
        tree = parser.parse(bytes(source, "utf8"))
        lines = source.splitlines()

        DEF_TYPES: dict[str, set[str]] = {
            "python": {"function_definition", "class_definition"},
            "java": {"method_declaration", "class_declaration", "constructor_declaration", "interface_declaration"},
            "go": {"function_declaration", "method_declaration"},
            "javascript": {"function_declaration", "arrow_function", "method_definition"},
            "typescript": {"function_declaration", "arrow_function", "method_definition"},
        }
        target_types = DEF_TYPES.get(lang, set())
        symbol_bytes = symbol.encode()

        def find_node(node):
            if node.type in target_types:
                for child in node.children:
                    if child.type in ("identifier", "field_identifier", "name") and child.text == symbol_bytes:
                        start = node.start_point[0]
                        end = node.end_point[0] + 1
                        return lines[start:end]
            for child in node.children:
                result = find_node(child)
                if result is not None:
                    return result
            return None

        return find_node(tree.root_node)
    except Exception:
        return None


def _find_enclosing_def(lines_all: list[str], i: int) -> int | None:
    """Walk backwards from line i to find the nearest enclosing function/method/class definition."""
    for j in range(i - 1, -1, -1):
        if re.match(r"\s*(def |class |func |public |private |protected |static )\w+", lines_all[j]):
            return j
    return None


def _is_trivial_diff(patch: str) -> bool:
    """Return True if all changed lines are whitespace or comments only."""
    changed = [
        line[1:]
        for line in patch.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    return bool(changed) and all(
        not c.strip() or c.strip().startswith(("#", "//", "*", "--", "/*", "*/"))
        for c in changed
    )


def _parse_hunk_context(patch: str) -> str:
    """Annotate diff hunk headers with the enclosing function/class name when present."""
    lines = []
    for line in patch.splitlines():
        if line.startswith("@@"):
            m = re.search(r"@@[^@]+@@\s*(.*)", line)
            ctx = m.group(1).strip() if m else ""
            lines.append(f"{line}  # in: {ctx}" if ctx else line)
        else:
            lines.append(line)
    return "\n".join(lines)


def _extract_block(lines_all: list[str], i: int, cap: int = 60) -> list[str]:
    """Extract a full indented block (function/class body) starting at line i."""
    base_indent = len(lines_all[i]) - len(lines_all[i].lstrip())
    block = [lines_all[i]]
    for line in lines_all[i + 1 : i + cap]:
        if line.strip() == "":
            block.append(line)
            continue
        if len(line) - len(line.lstrip()) <= base_indent:
            break
        block.append(line)
    return block


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
        patch = f.get("patch", "")
        trivial = " (trivial: whitespace/comments only — consider skipping)" if patch and _is_trivial_diff(patch) else ""
        lines.append(f"### {f['filename']} ({f['status']}, +{f['additions']} -{f['deletions']}){trivial}")
        if patch:
            lines.append(_parse_hunk_context(patch))
        else:
            lines.append("(binary or no diff available)")
        lines.append("")

    return "\n".join(lines)


@tool
def search_code_symbol(symbol: str, repo_url: str, callers_only: bool = False) -> str:
    """Search for a function, class, or variable in a GitHub repository.

    symbol: the function, class, or variable name to search for.
    repo_url: e.g. 'https://alm-github.my-company.com/org/repo'
    callers_only: if False (default), find the definition and return its full body.
                  if True, skip the definition and return the enclosing function body
                  of each call site — use this to find who calls a changed function
                  and assess blast radius.
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
                lang = _detect_language(path)
                for i, line in enumerate(lines_all):
                    if symbol not in line:
                        continue
                    is_def = bool(re.match(rf"\s*(def |class |func )\s*{re.escape(symbol)}", line))
                    if callers_only and is_def:
                        continue  # skip the definition, look for call sites
                    if not callers_only and not is_def and any(
                        symbol in l and re.match(rf"\s*(def |class |func )\s*{re.escape(symbol)}", l)
                        for l in lines_all
                    ):
                        # definition exists elsewhere in this file, skip call sites
                        continue
                    if callers_only:
                        enc_i = _find_enclosing_def(lines_all, i)
                        if enc_i is not None:
                            block = _extract_block_ast(raw, lines_all[enc_i].strip().split("(")[0].split()[-1], lang or "")
                            snippet_lines = block if block else _extract_block(lines_all, enc_i)
                            start = enc_i
                            label = lines_all[enc_i].strip()
                            results.append(f"called in: `{label}`")
                        else:
                            start = max(0, i - 10)
                            snippet_lines = lines_all[start:min(len(lines_all), i + 11)]
                    elif is_def:
                        block = _extract_block_ast(raw, symbol, lang or "")
                        snippet_lines = block if block else _extract_block(lines_all, i)
                        start = i
                    else:
                        start = max(0, i - 10)
                        snippet_lines = lines_all[start:min(len(lines_all), i + 11)]
                    snippet = "\n".join(f"{start + j + 1}: {l}" for j, l in enumerate(snippet_lines))
                    results.append(f"```\n{snippet}\n```")
                    break
            else:
                results.append("(could not fetch snippet)")
    return "\n".join(results)


@tool
def get_file_content(file_path: str, repo_url: str, ref: str = None, start_line: int = 1, window: int = 200) -> str:
    """Get the content of a file from a GitHub repository.

    file_path: relative path in the repo, e.g. 'src/utils/helper.py'
    repo_url: e.g. 'https://alm-github.my-company.com/org/repo'
    ref: branch or commit SHA. Pass the PR head branch to see current state.
    start_line: first line to return (1-indexed, default 1).
    window: number of lines to return (default 200). Use a smaller window when
            you know the relevant line number from the diff.
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
    start = max(0, start_line - 1)
    end = min(len(lines), start + window)
    result = "\n".join(f"{start + j + 1}: {l}" for j, l in enumerate(lines[start:end]))
    if end < len(lines):
        result += f"\n\n... (truncated, {len(lines)} lines total)"
    return result


@tool
def get_pr_comments(pr_url: str) -> str:
    """Fetch existing review comments on a GitHub Pull Request.

    Call this before starting a review to avoid repeating issues already raised.
    Returns both inline review comments (on specific lines) and general PR comments.

    pr_url: full URL of the pull request.
    """
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        return "GITHUB_TOKEN is not set."

    match = re.match(r"https?://([^/]+)/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        return f"Invalid PR URL format: {pr_url}"

    host, owner, repo, pr_number = match.groups()
    api_base = f"https://{host}/api/v3"
    headers = _github_headers(github_token)

    with httpx.Client(verify=False) as client:
        inline_resp = client.get(
            f"{api_base}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            headers=headers,
            params={"per_page": 50},
        )
        general_resp = client.get(
            f"{api_base}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=headers,
            params={"per_page": 50},
        )

    lines = []

    if inline_resp.status_code == 200:
        inline = inline_resp.json()
        if inline:
            lines.append(f"### Inline review comments ({len(inline)})")
            for c in inline:
                author = c.get("user", {}).get("login", "?")
                path = c.get("path", "")
                position = c.get("original_line") or c.get("line") or "?"
                body = c.get("body", "").strip()
                lines.append(f"{author} on {path}:{position} — {body}")
            lines.append("")

    if general_resp.status_code == 200:
        general = general_resp.json()
        if general:
            lines.append(f"### General comments ({len(general)})")
            for c in general:
                author = c.get("user", {}).get("login", "?")
                body = c.get("body", "").strip()
                lines.append(f"{author}: {body}")

    return "\n".join(lines) if lines else "No existing comments."


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
