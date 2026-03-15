"""
Senior Engineer Prompt Library

All Claude prompts for PR-Optic in one place for easy iteration and tuning.
When the agent gives bad feedback, tune the prompt here — not the orchestrator.

Principles:
- Explain WHY not just WHAT
- Be constructive not critical
- Skip formatting/whitespace/naming unless it causes a real bug
- Check: hardcoded secrets, missing env vars, error handling, edge cases
"""

from typing import List
from src.models.github import PRFile
from src.models.state import IssueItem


# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

SENIOR_ENGINEER_SYSTEM = """You are a senior software engineer conducting a code review.

Your review philosophy:
- **Explain WHY, not just WHAT**: Every comment should teach, not just point out issues
- **Be constructive, not critical**: Frame feedback as opportunities for improvement
- **Focus on real bugs**: Skip minor formatting, whitespace, or naming unless it causes actual problems
- **Prioritize security and reliability**: Hardcoded secrets, missing error handling, and untested edge cases are critical

What you MUST check:
✓ Hardcoded secrets, API keys, passwords, or URLs
✓ Missing environment variables for configuration
✓ Functions that should be reusable but aren't
✓ Missing error handling (try/catch, null checks, validation)
✓ Untested edge cases (empty arrays, null values, boundary conditions)
✓ Security vulnerabilities (SQL injection, XSS, CSRF, etc.)

What you SHOULD SKIP:
✗ Minor formatting issues (unless they break linting)
✗ Whitespace or indentation preferences
✗ Variable naming (unless truly confusing)
✗ Subjective style preferences

Your tone: Professional, helpful, and educational. You're mentoring, not judging."""


TRIAGE_SYSTEM = """You are a senior software engineer performing initial PR triage.

Your job: Quickly scan the PR and identify which concern categories need deeper review.

Categories to check:
- **security**: Hardcoded secrets, SQL injection, XSS, authentication issues
- **error_handling**: Missing try/catch, no null checks, unhandled edge cases
- **maintainability**: Duplicate code, overly complex functions, poor separation of concerns
- **hardcoded_values**: Hardcoded URLs, API keys, configuration that should be env vars
- **performance**: N+1 queries, inefficient algorithms, memory leaks
- **testing**: Missing tests for new features, untested edge cases

Return JSON only. Be conservative: if unsure, include the category for focused review."""


VERIFICATION_SYSTEM = """You are a senior software engineer verifying if developer fixes adequately address the issues you previously raised.

Your job: For each issue, determine if the fix is:
1. **Present**: Was the issue actually addressed in this commit?
2. **Adequate**: Is the fix correct and complete?
3. **Safe**: Does the fix introduce new problems?

Be thorough but fair. If the developer made a good-faith effort to fix the issue, mark it as fixed.

Return JSON only with your verification results."""


# ============================================================================
# TRIAGE PROMPT
# ============================================================================

def build_triage_prompt(files: List[PRFile]) -> dict:
    """Build triage prompt for initial PR scan.
    
    Args:
        files: List of changed files in the PR
        
    Returns:
        Dict with 'system' and 'user' prompts
    """
    # Build file summary
    file_summaries = []
    for file in files[:20]:  # Limit to first 20 files
        # Infer language from filename extension
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'text'
        lang_map = {'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'java': 'java', 'go': 'go', 'rb': 'ruby'}
        language = lang_map.get(ext, ext)
        
        file_summaries.append(
            f"**{file.filename}** ({file.status}, +{file.additions}/-{file.deletions})\n"
            f"```{language}\n{file.patch[:2000]}\n```"
        )
    
    files_text = "\n\n".join(file_summaries)
    
    if len(files) > 20:
        files_text += f"\n\n... and {len(files) - 20} more files"
    
    user_prompt = f"""Review this pull request and identify which concern categories need focused review.

## Changed Files ({len(files)} total)

{files_text}

## Your Task

Scan the changes and determine which categories need deeper review. Return JSON:

```json
{{
  "categories_to_review": ["security", "error_handling", "maintainability"],
  "reasoning": "Found hardcoded API key in config.py (security), missing error handling in api.py (error_handling), and duplicate code across multiple files (maintainability)"
}}
```

Categories available:
- security
- error_handling
- maintainability
- hardcoded_values
- performance
- testing

Be conservative: if you see potential issues, include the category."""
    
    return {
        "system": TRIAGE_SYSTEM,
        "user": user_prompt
    }


# ============================================================================
# FOCUSED REVIEW PROMPT
# ============================================================================

def build_review_prompt(files: List[PRFile], category: str) -> dict:
    """Build focused review prompt for one concern category.
    
    Args:
        files: List of changed files in the PR
        category: Concern category to focus on
        
    Returns:
        Dict with 'system' and 'user' prompts
    """
    # Category-specific guidance
    category_guidance = {
        "security": """Focus on:
- Hardcoded secrets, API keys, passwords, or tokens
- SQL injection vulnerabilities (string concatenation in queries)
- XSS vulnerabilities (unescaped user input in HTML)
- Authentication/authorization bypasses
- Insecure cryptography or hashing
- Path traversal vulnerabilities
- CSRF vulnerabilities in forms""",
        
        "error_handling": """Focus on:
- Missing try/catch blocks around risky operations
- No null/undefined checks before accessing properties
- Unhandled promise rejections
- Missing validation for user input
- No error messages for users
- Silent failures (catching errors without logging)
- Untested edge cases (empty arrays, null values, boundary conditions)""",
        
        "maintainability": """Focus on:
- Duplicate code that should be extracted to functions
- Functions longer than 50 lines that should be split
- Poor separation of concerns (mixing business logic with UI)
- Magic numbers that should be named constants
- Complex conditionals that need simplification
- Missing documentation for complex logic""",
        
        "hardcoded_values": """Focus on:
- Hardcoded URLs that should be environment variables
- Hardcoded API endpoints
- Hardcoded configuration values
- Hardcoded file paths
- Hardcoded database connection strings
- Any value that differs between dev/staging/production""",
        
        "performance": """Focus on:
- N+1 query problems (loops with database calls)
- Inefficient algorithms (O(n²) when O(n) is possible)
- Missing database indexes
- Loading entire datasets when pagination is needed
- Memory leaks (event listeners not cleaned up)
- Unnecessary re-renders or re-computations""",
        
        "testing": """Focus on:
- New features without tests
- Changed functions without updated tests
- Missing edge case tests (null, empty, boundary values)
- Missing error case tests
- Integration tests for critical paths
- Missing test coverage for security-sensitive code"""
    }
    
    guidance = category_guidance.get(category, "Review for potential issues in this category.")
    
    # Build file content
    file_contents = []
    for file in files[:15]:  # Limit to first 15 files
        # Infer language from filename extension
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'text'
        lang_map = {'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'java': 'java', 'go': 'go', 'rb': 'ruby'}
        language = lang_map.get(ext, ext)
        
        file_contents.append(
            f"### {file.filename} ({file.status})\n\n"
            f"```{language}\n{file.patch[:3000]}\n```"
        )
    
    files_text = "\n\n".join(file_contents)
    
    if len(files) > 15:
        files_text += f"\n\n... and {len(files) - 15} more files"
    
    user_prompt = f"""Perform a focused **{category}** review of this pull request.

{guidance}

## Changed Files

{files_text}

## Your Task

Review the code for **{category}** issues. For each issue found:

1. **Explain WHY it's a problem** (not just what's wrong)
2. **Suggest a specific fix** (with code example if helpful)
3. **Indicate severity**: CRITICAL (breaks security/functionality), MAJOR (should fix before merge), or MINOR (nice to have)

Return JSON:

```json
{{
  "issues": [
    {{
      "file": "src/api.py",
      "line": 42,
      "severity": "CRITICAL",
      "category": "{category}",
      "title": "Hardcoded API key exposes credentials",
      "explanation": "The API key is hardcoded in the source code, which means it will be committed to version control and visible to anyone with repository access. If this key is compromised, attackers can make unauthorized API calls.",
      "suggested_fix": "Move the API key to an environment variable:\\n\\n```python\\nimport os\\nAPI_KEY = os.getenv('OPENAI_API_KEY')\\nif not API_KEY:\\n    raise ValueError('OPENAI_API_KEY environment variable is required')\\n```"
    }}
  ]
}}
```

**Important**: 
- Skip minor formatting/naming issues unless they cause real problems
- Focus on issues that impact security, reliability, or maintainability
- Be constructive: frame feedback as learning opportunities
- If no issues found, return empty issues array"""
    
    return {
        "system": SENIOR_ENGINEER_SYSTEM,
        "user": user_prompt
    }

def build_verification_prompt(
    issues: List[IssueItem],
    new_diff: str,
    category: str
) -> dict:
    """Build verification prompt for checking if fixes are adequate.
    
    Args:
        issues: List of issues to verify
        new_diff: New commit diff to analyze
        category: Category of issues being verified
        
    Returns:
        Dict with 'system' and 'user' prompts
    """
    # Build issues list
    issues_text = []
    for i, issue in enumerate(issues, 1):
        issues_text.append(
            f"**Issue {i}: {issue.id}**\n"
            f"- **File**: {issue.file}:{issue.line}\n"
            f"- **Category**: {issue.category}\n"
            f"- **Problem**: {issue.body}\n"
            f"- **Suggested Fix**: {issue.suggested_fix or 'Not provided'}\n"
        )
    
    issues_list = "\n".join(issues_text)
    
    # Limit diff size
    diff_preview = new_diff[:8000]
    if len(new_diff) > 8000:
        diff_preview += "\n\n... (diff truncated)"
    
    user_prompt = f"""I previously raised {len(issues)} **{category}** issue(s) in this PR. The developer has pushed a new commit. Please verify if each issue was adequately addressed.

## Issues I Raised

{issues_list}

## New Commit Diff

```diff
{diff_preview}
```

## Your Task

For each issue, determine:
1. **Was the issue fixed in this commit?** (Is there evidence in the diff?)
2. **Is the fix adequate and correct?** (Does it properly address the root cause?)
3. **Does the fix introduce new problems?** (Any regressions or new issues?)

Return JSON in this exact format:

```json
{{
  "verifications": [
    {{
      "issue_id": "{issues[0].id if issues else 'file.py:10:security'}",
      "is_fixed": true,
      "comment": "SQL injection fixed by using parameterized queries. The developer correctly replaced string concatenation with prepared statements, which prevents SQL injection attacks.",
      "confidence": 0.95
    }}
  ]
}}
```

**Guidelines**:
- Be thorough but fair
- If the developer made a good-faith effort to fix the issue, mark it as fixed
- Confidence: 0.0-1.0 (how certain are you about the fix?)
- Comment should explain your reasoning

Return one verification per issue."""
    
    return {
        "system": VERIFICATION_SYSTEM,
        "user": user_prompt
    }


# ============================================================================
# COMMENT TEMPLATES
# ============================================================================

def build_approval_comment(
    fixed_issues: List[IssueItem],
    verifications: list
) -> str:
    """Build approval comment template.
    
    Args:
        fixed_issues: List of issues that were fixed
        verifications: List of verification results
        
    Returns:
        Formatted approval comment
    """
    if not fixed_issues:
        return """## ✅ Code Review: APPROVED

Great work! The code looks good and is ready to merge.

**PR-Optic** - AI-powered code review
"""
    
    # Build fixed issues list
    fixed_list = []
    for issue in fixed_issues:
        # Find verification for this issue
        verification = next(
            (v for v in verifications if v.issue_id == issue.id),
            None
        )
        
        comment = verification.verification_comment if verification else "Issue resolved"
        
        fixed_list.append(
            f"- **{issue.file}:{issue.line}** ({issue.category}): {issue.body}\n"
            f"  *✅ Fixed:* {comment}"
        )
    
    fixed_text = "\n".join(fixed_list)
    
    return f"""## ✅ Code Review: APPROVED

🎉 Excellent work! All issues have been successfully resolved. The code is ready to merge.

### Issues Resolved ({len(fixed_issues)})

{fixed_text}

---

**PR-Optic** - AI-powered code review
"""


def build_rejection_comment(
    still_open_issues: List[IssueItem],
    fixed_count: int,
    verifications: list
) -> str:
    """Build rejection comment template (still has open issues).
    
    Args:
        still_open_issues: List of issues that are still open
        fixed_count: Number of issues that were fixed
        verifications: List of verification results
        
    Returns:
        Formatted rejection comment
    """
    # Build open issues list
    open_list = []
    for issue in still_open_issues:
        # Find verification for this issue
        verification = next(
            (v for v in verifications if v.issue_id == issue.id),
            None
        )
        
        if verification and not verification.is_fixed:
            reason = verification.verification_comment
        else:
            reason = "Not yet addressed"
        
        open_list.append(
            f"- **{issue.file}:{issue.line}** ({issue.category}): {issue.body}\n"
            f"  *Status:* {reason}\n"
            f"  *Suggested fix:* {issue.suggested_fix or 'See issue description'}"
        )
    
    open_text = "\n".join(open_list)
    
    # Add progress message if some were fixed
    progress_msg = ""
    if fixed_count > 0:
        progress_msg = f"\n✅ **Good progress!** You've fixed {fixed_count} issue(s). "
    
    return f"""## ⚠️ Code Review: CHANGES REQUESTED
{progress_msg}
However, there are still {len(still_open_issues)} issue(s) that need attention before this PR can be merged.

### Issues Still Open ({len(still_open_issues)})

{open_text}

---

**PR-Optic** - AI-powered code review
"""


def build_initial_review_comment(
    issues_by_severity: dict,
    total_issues: int,
    summary: str
) -> str:
    """Build initial review comment template.
    
    Args:
        issues_by_severity: Dict mapping severity to list of issues
        total_issues: Total number of issues found
        summary: Review summary
        
    Returns:
        Formatted review comment
    """
    if total_issues == 0:
        return """## ✅ Code Review: APPROVED

Great work! No issues found. The code looks good and is ready to merge.

**PR-Optic** - AI-powered code review
"""
    
    # Build issues by severity
    severity_sections = []
    
    for severity in ["CRITICAL", "MAJOR", "MINOR"]:
        issues = issues_by_severity.get(severity, [])
        if not issues:
            continue
        
        emoji = {"CRITICAL": "🚨", "MAJOR": "⚠️", "MINOR": "💡"}[severity]
        
        issue_list = []
        for issue in issues:
            issue_list.append(
                f"- **{issue['file']}:{issue['line']}** ({issue['category']}): {issue['title']}\n"
                f"  {issue['explanation']}\n"
                f"  *Suggested fix:* {issue['suggested_fix']}"
            )
        
        issues_text = "\n\n".join(issue_list)
        
        severity_sections.append(
            f"### {emoji} {severity} Issues ({len(issues)})\n\n{issues_text}"
        )
    
    sections_text = "\n\n".join(severity_sections)
    
    return f"""## ⚠️ Code Review: CHANGES REQUESTED

{summary}

{sections_text}

---

**PR-Optic** - AI-powered code review
"""
