"""
Comment Formatter - Professional Senior Engineer Style

Formats review comments to look like a senior engineer's review:
- No emojis or decorative elements
- Clear, professional language
- Line-specific inline comments
- Constructive explanations with WHY
"""

from src.models.review import ReviewComment, Severity


def format_inline_comment(comment: ReviewComment) -> str:
    """Format a single inline comment for GitHub posting.
    
    This creates professional, senior engineer-style comments without emojis.
    
    Args:
        comment: Review comment to format
        
    Returns:
        Formatted comment body ready for GitHub
    """
    # Build the comment without emojis
    parts = []
    
    # Severity indicator (text only, no emojis)
    severity_text = {
        Severity.CRITICAL: "CRITICAL",
        Severity.MAJOR: "MAJOR", 
        Severity.MINOR: "MINOR"
    }.get(comment.severity, "ISSUE")
    
    # Category
    category_text = comment.category.replace('_', ' ').title()
    
    # Header
    parts.append(f"**{severity_text}: {category_text}**")
    parts.append("")
    
    # Problem description
    parts.append("**Why this is a problem:**")
    parts.append(comment.body)
    parts.append("")
    
    # Impact
    impact_level = {
        Severity.CRITICAL: "CRITICAL - Security vulnerability or data loss risk",
        Severity.MAJOR: "MAJOR - Functionality, maintainability, or performance issue",
        Severity.MINOR: "MINOR - Code quality improvement"
    }.get(comment.severity, "Issue that should be addressed")
    
    parts.append(f"**Impact:** {impact_level}")
    parts.append("")
    
    # Suggested fix
    if comment.suggested_fix:
        parts.append("**Suggested fix:**")
        parts.append("```")
        parts.append(comment.suggested_fix)
        parts.append("```")
    
    parts.append("")
    parts.append("Reviewed by PR-Optic")
    
    return "\n".join(parts)


def format_review_summary(
    total_issues: int,
    issues_by_severity: dict,
    issues_by_category: dict,
    summary: str
) -> str:
    """Format overall review summary comment.
    
    Args:
        total_issues: Total number of issues found
        issues_by_severity: Dict mapping severity to issue count
        issues_by_category: Dict mapping category to issue count
        summary: AI-generated summary
        
    Returns:
        Formatted summary for GitHub review
    """
    parts = []
    
    # Header
    parts.append("## Code Review Summary")
    parts.append("")
    
    # Overview
    if total_issues == 0:
        parts.append("No issues found. The code looks good!")
        parts.append("")
        parts.append("**Recommendation:** APPROVE")
        return "\n".join(parts)
    
    parts.append(f"Found {total_issues} issue(s) that need attention.")
    parts.append("")
    
    # Summary from AI
    parts.append("**Summary:**")
    parts.append(summary)
    parts.append("")
    
    # Breakdown by severity
    if issues_by_severity:
        parts.append("**Issues by Severity:**")
        for severity in [Severity.CRITICAL, Severity.MAJOR, Severity.MINOR]:
            count = issues_by_severity.get(severity, 0)
            if count > 0:
                parts.append(f"- {severity.value.upper()}: {count}")
        parts.append("")
    
    # Breakdown by category
    if issues_by_category:
        parts.append("**Issues by Category:**")
        for category, count in sorted(issues_by_category.items()):
            category_name = category.replace('_', ' ').title()
            parts.append(f"- {category_name}: {count}")
        parts.append("")
    
    # Next steps
    parts.append("**Next Steps:**")
    parts.append("Please review the inline comments on specific lines for detailed feedback and suggested fixes.")
    parts.append("")
    
    # Recommendation
    has_critical = issues_by_severity.get(Severity.CRITICAL, 0) > 0
    if has_critical:
        parts.append("**Recommendation:** REQUEST CHANGES (critical issues must be addressed)")
    else:
        parts.append("**Recommendation:** REQUEST CHANGES (please address the issues above)")
    
    return "\n".join(parts)


def format_verification_summary(
    total_issues: int,
    fixed_count: int,
    still_open: int,
    verifications: list,
    all_fixed: bool
) -> str:
    """Format fix verification summary.
    
    Args:
        total_issues: Total issues that were checked
        fixed_count: Number of issues that were fixed
        still_open: Number of issues still open
        verifications: List of verification results
        all_fixed: Whether all issues are fixed
        
    Returns:
        Formatted verification summary
    """
    parts = []
    
    # Header
    parts.append("## Fix Verification Results")
    parts.append("")
    
    # Progress
    parts.append(f"**Progress:** {fixed_count}/{total_issues} issues resolved")
    parts.append("")
    
    if all_fixed:
        # All fixed - approval
        parts.append("**Status:** All previously identified issues have been successfully addressed.")
        parts.append("")
        parts.append("**Resolved Issues:**")
        for ver in verifications:
            if ver.is_fixed:
                parts.append(f"- {ver.issue_id}: {ver.verification_comment}")
        parts.append("")
        parts.append("**Recommendation:** APPROVE - Great work addressing all the feedback!")
    else:
        # Some still open
        parts.append(f"**Status:** Good progress! {fixed_count} issue(s) resolved, but {still_open} still need attention.")
        parts.append("")
        
        # Show what was fixed
        fixed_items = [v for v in verifications if v.is_fixed]
        if fixed_items:
            parts.append("**Resolved Issues:**")
            for ver in fixed_items:
                parts.append(f"- {ver.issue_id}: {ver.verification_comment}")
            parts.append("")
        
        # Show what's still open
        open_items = [v for v in verifications if not v.is_fixed]
        if open_items:
            parts.append("**Still Open:**")
            for ver in open_items:
                parts.append(f"- {ver.issue_id}: {ver.verification_comment}")
            parts.append("")
        
        parts.append("**Recommendation:** REQUEST CHANGES (please address remaining issues)")
    
    return "\n".join(parts)


def format_approval_comment() -> str:
    """Format approval comment when no issues found.
    
    Returns:
        Formatted approval comment
    """
    parts = []
    parts.append("## Code Review Summary")
    parts.append("")
    parts.append("The code has been reviewed and looks good. No issues found.")
    parts.append("")
    parts.append("**Recommendation:** APPROVE")
    return "\n".join(parts)
