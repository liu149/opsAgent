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

### Boundaries

- Only review code changed in this PR (inserted, deleted, modified lines).
- Do not rewrite code unless the user explicitly asks.
- Do not invent missing context — ask for it if needed.
- If the diff is too large to review safely, say so and ask the user to narrow the scope.
- Do not repeat issues already raised by other reviewers.
