Fetch a GitHub Pull Request diff and analyze it as a code review.

Example: pr_url='https://alm-github.my-company.com/my-project/my-repo/pull/1'

After fetching the diff, analyze it across these dimensions:
1. Code Style & Formatting - naming conventions, indentation, unnecessary whitespace, dead code
2. Logic & Correctness - bugs, off-by-one errors, null/empty checks, incorrect conditions
3. Security - injection risks, hardcoded secrets, insecure dependencies, improper auth/permission checks
4. Performance - unnecessary loops, missing indexes, N+1 queries, redundant computation
5. Maintainability - overly complex logic, missing error handling, magic numbers, code duplication

Output format:

## PR Review: <PR title>

### Summary
<2-3 sentences overall assessment>

### Issues

| Severity | File | Line | Dimension | Description |
|----------|------|------|-----------|-------------|
| 🔴 Critical   | path/to/file.py | 42 | Security    | Hardcoded password exposed              |
| 🟠 Major      | path/to/file.py | 87 | Logic       | Null check missing before dereferencing |
| 🟡 Minor      | path/to/file.py | 12 | Style       | Variable name `x` is not descriptive   |
| 🔵 Suggestion | path/to/file.py | 55 | Performance | Consider caching this result            |

### Conclusion
<Pass or Request Changes, with brief reason>

If there are no issues found in a dimension, omit it from the table. If the diff is clean, say so explicitly.
