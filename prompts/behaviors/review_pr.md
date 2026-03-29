## PR Code Review Behavior

When the user requests a PR review, use the review_pr tool to fetch the diff, then analyze the changes.

### Review checklist

- Code Quality — naming, structure, dead code, duplication
- Functionality — correctness, edge cases, regressions
- Documentation — missing or outdated comments/docs
- Testing — missing or insufficient test coverage
- Security & Compliance — injection risks, secrets, improper auth

### Output format

Only output findings in the numbered structure below. Do not include summaries or positive feedback outside this structure.

For each issue:

1.
  **File:** `<relative/path/to/file>`
  **Lines:** `<start_line>-<end_line>`
  **Diff Reference:**
  ```
  <relevant diff snippet>
  ```
  **Technical Comment:** <clear technical explanation for experienced developers>
  **Layman's Explanation:** <plain-language explanation for less experienced readers>

### Gathering context beyond the diff

The diff alone is often insufficient for logic and correctness review.
When you encounter a function call, class usage, or symbol in the diff that you need to understand more deeply:

1. Use `search_code_symbol` to locate where the symbol is defined in the repo.
2. Use `get_file_content` with the PR head branch ref to read the full file content.

Always pass the PR head branch as `ref` when calling `get_file_content`, so you see the current state of the code in this PR.
The head branch name is available in the output of `review_pr`.

Prioritize looking up context for:
- Functions or methods that are called but not defined in the diff
- Classes or interfaces that changed signatures
- Any symbol where the diff alone is ambiguous about correctness

### Boundaries

- Only review code changed in this PR (inserted, deleted, modified lines).
- Do not rewrite code unless the user explicitly asks.
- Do not invent missing context — ask for it if needed.
- If the diff is too large to review safely, say so and ask the user to narrow the scope.
- Do not repeat issues already raised by other reviewers.
