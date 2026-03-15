"""Tests for senior review prompt library."""

import pytest
from src.prompts.senior_review import (
    build_triage_prompt,
    build_review_prompt,
    build_verification_prompt,
    build_approval_comment,
    build_rejection_comment,
    build_initial_review_comment,
)
from src.models.github import PRFile
from src.models.state import IssueItem


@pytest.fixture
def sample_files():
    """Sample PR files for testing."""
    return [
        PRFile(
            filename="src/api.py",
            status="modified",
            additions=10,
            deletions=5,
            changes=15,
            patch="@@ -1,5 +1,10 @@\n+import os\n+API_KEY = os.getenv('API_KEY')",
            sha="abc123",
            blob_url="https://github.com/test/repo/blob/abc123/src/api.py",
            raw_url="https://github.com/test/repo/raw/abc123/src/api.py",
            contents_url="https://api.github.com/repos/test/repo/contents/src/api.py"
        ),
        PRFile(
            filename="src/config.py",
            status="added",
            additions=20,
            deletions=0,
            changes=20,
            patch="@@ -0,0 +1,20 @@\n+DATABASE_URL = 'postgresql://localhost'",
            sha="def456",
            blob_url="https://github.com/test/repo/blob/def456/src/config.py",
            raw_url="https://github.com/test/repo/raw/def456/src/config.py",
            contents_url="https://api.github.com/repos/test/repo/contents/src/config.py"
        )
    ]


@pytest.fixture
def sample_issues():
    """Sample issues for testing."""
    return [
        IssueItem(
            id="api.py:10:security",
            category="security",
            file="src/api.py",
            line=10,
            body="Hardcoded API key",
            suggested_fix="Use environment variable",
            resolved=False,
            round_raised=1
        ),
        IssueItem(
            id="config.py:5:hardcoded_values",
            category="hardcoded_values",
            file="src/config.py",
            line=5,
            body="Hardcoded database URL",
            suggested_fix="Use DATABASE_URL env var",
            resolved=False,
            round_raised=1
        )
    ]


class TestTriagePrompt:
    """Test triage prompt building."""
    
    def test_build_triage_prompt_structure(self, sample_files):
        """Test that triage prompt has correct structure."""
        result = build_triage_prompt(sample_files)
        
        assert "system" in result
        assert "user" in result
        assert isinstance(result["system"], str)
        assert isinstance(result["user"], str)
    
    def test_triage_prompt_includes_files(self, sample_files):
        """Test that triage prompt includes file information."""
        result = build_triage_prompt(sample_files)
        
        assert "src/api.py" in result["user"]
        assert "src/config.py" in result["user"]
        assert "modified" in result["user"]
        assert "added" in result["user"]
    
    def test_triage_prompt_mentions_categories(self, sample_files):
        """Test that triage prompt mentions concern categories."""
        result = build_triage_prompt(sample_files)
        
        assert "security" in result["user"]
        assert "error_handling" in result["user"]
        assert "maintainability" in result["user"]
    
    def test_triage_system_prompt_sets_expectations(self, sample_files):
        """Test that system prompt sets correct expectations."""
        result = build_triage_prompt(sample_files)
        
        assert "senior" in result["system"].lower()
        assert "triage" in result["system"].lower()
        assert "JSON" in result["system"]


class TestReviewPrompt:
    """Test focused review prompt building."""
    
    def test_build_review_prompt_structure(self, sample_files):
        """Test that review prompt has correct structure."""
        result = build_review_prompt(sample_files, "security")
        
        assert "system" in result
        assert "user" in result
    
    def test_review_prompt_includes_category_guidance(self, sample_files):
        """Test that review prompt includes category-specific guidance."""
        result = build_review_prompt(sample_files, "security")
        
        assert "security" in result["user"].lower()
        assert "hardcoded" in result["user"].lower() or "SQL injection" in result["user"]
    
    def test_review_prompt_includes_files(self, sample_files):
        """Test that review prompt includes file content."""
        result = build_review_prompt(sample_files, "security")
        
        assert "src/api.py" in result["user"]
        assert "API_KEY" in result["user"]
    
    def test_review_prompt_enforces_why_not_what(self, sample_files):
        """Test that review prompt enforces explaining WHY."""
        result = build_review_prompt(sample_files, "security")
        
        assert "WHY" in result["user"] or "why" in result["user"].lower()
        assert "Explain" in result["user"] or "explain" in result["user"].lower()
    
    def test_review_prompt_skips_minor_issues(self, sample_files):
        """Test that review prompt instructs to skip minor formatting."""
        result = build_review_prompt(sample_files, "security")
        
        system_and_user = result["system"] + result["user"]
        assert "formatting" in system_and_user.lower() or "whitespace" in system_and_user.lower()
    
    def test_review_prompt_checks_hardcoded_secrets(self, sample_files):
        """Test that security prompt checks for hardcoded secrets."""
        result = build_review_prompt(sample_files, "security")
        
        assert "hardcoded" in result["user"].lower()
        assert "secret" in result["user"].lower() or "API key" in result["user"] or "password" in result["user"]
    
    def test_review_prompt_checks_error_handling(self, sample_files):
        """Test that error_handling prompt checks for missing error handling."""
        result = build_review_prompt(sample_files, "error_handling")
        
        assert "error" in result["user"].lower()
        assert "try" in result["user"].lower() or "catch" in result["user"].lower() or "null" in result["user"].lower()


class TestVerificationPrompt:
    """Test fix verification prompt building."""
    
    def test_build_verification_prompt_structure(self, sample_issues):
        """Test that verification prompt has correct structure."""
        result = build_verification_prompt(
            issues=sample_issues,
            new_diff="diff --git a/api.py...",
            category="security"
        )
        
        assert "system" in result
        assert "user" in result
    
    def test_verification_prompt_includes_issues(self, sample_issues):
        """Test that verification prompt includes issue details."""
        result = build_verification_prompt(
            issues=sample_issues,
            new_diff="diff --git a/api.py...",
            category="security"
        )
        
        assert "api.py:10:security" in result["user"]
        assert "Hardcoded API key" in result["user"]
        assert "Use environment variable" in result["user"]
    
    def test_verification_prompt_includes_diff(self, sample_issues):
        """Test that verification prompt includes commit diff."""
        diff = "diff --git a/api.py\n+API_KEY = os.getenv('API_KEY')"
        result = build_verification_prompt(
            issues=sample_issues,
            new_diff=diff,
            category="security"
        )
        
        assert "API_KEY = os.getenv" in result["user"]
    
    def test_verification_prompt_asks_for_json(self, sample_issues):
        """Test that verification prompt requests JSON response."""
        result = build_verification_prompt(
            issues=sample_issues,
            new_diff="diff...",
            category="security"
        )
        
        assert "JSON" in result["user"] or "json" in result["user"]
        assert "verifications" in result["user"]
    
    def test_verification_system_prompt_is_fair(self, sample_issues):
        """Test that system prompt instructs to be fair."""
        result = build_verification_prompt(
            issues=sample_issues,
            new_diff="diff...",
            category="security"
        )
        
        assert "fair" in result["system"].lower() or "fair" in result["user"].lower()


class TestApprovalComment:
    """Test approval comment template."""
    
    def test_approval_comment_with_no_issues(self):
        """Test approval comment when no issues were raised."""
        result = build_approval_comment([], [])
        
        assert "APPROVED" in result
        assert "Great work" in result or "good" in result.lower()
    
    def test_approval_comment_lists_fixed_issues(self, sample_issues):
        """Test that approval comment lists resolved issues."""
        # Mark issues as resolved
        for issue in sample_issues:
            issue.resolved = True
        
        verifications = [
            type('obj', (object,), {
                'issue_id': 'api.py:10:security',
                'verification_comment': 'Fixed by using env var'
            })(),
            type('obj', (object,), {
                'issue_id': 'config.py:5:hardcoded_values',
                'verification_comment': 'Fixed by using DATABASE_URL'
            })()
        ]
        
        result = build_approval_comment(sample_issues, verifications)
        
        assert "APPROVED" in result
        assert "api.py:10" in result
        assert "config.py:5" in result
        assert "Fixed" in result


class TestRejectionComment:
    """Test rejection comment template."""
    
    def test_rejection_comment_lists_open_issues(self, sample_issues):
        """Test that rejection comment lists still-open issues."""
        verifications = [
            type('obj', (object,), {
                'issue_id': 'api.py:10:security',
                'is_fixed': False,
                'verification_comment': 'Still hardcoded'
            })(),
            type('obj', (object,), {
                'issue_id': 'config.py:5:hardcoded_values',
                'is_fixed': False,
                'verification_comment': 'Still hardcoded'
            })()
        ]
        
        result = build_rejection_comment(sample_issues, 0, verifications)
        
        assert "CHANGES REQUESTED" in result
        assert "api.py:10" in result
        assert "config.py:5" in result
    
    def test_rejection_comment_shows_progress(self, sample_issues):
        """Test that rejection comment shows progress if some fixed."""
        verifications = [
            type('obj', (object,), {
                'issue_id': 'api.py:10:security',
                'is_fixed': False,
                'verification_comment': 'Still hardcoded'
            })()
        ]
        
        result = build_rejection_comment([sample_issues[0]], 1, verifications)
        
        assert "progress" in result.lower() or "fixed 1" in result.lower()


class TestInitialReviewComment:
    """Test initial review comment template."""
    
    def test_initial_review_comment_with_no_issues(self):
        """Test initial review comment when no issues found."""
        result = build_initial_review_comment({}, 0, "No issues found")
        
        assert "APPROVED" in result
        assert "No issues" in result
    
    def test_initial_review_comment_groups_by_severity(self):
        """Test that initial review comment groups issues by severity."""
        issues_by_severity = {
            "CRITICAL": [
                {
                    "file": "api.py",
                    "line": 10,
                    "category": "security",
                    "title": "SQL injection",
                    "explanation": "Vulnerable to SQL injection",
                    "suggested_fix": "Use parameterized queries"
                }
            ],
            "MAJOR": [
                {
                    "file": "app.py",
                    "line": 20,
                    "category": "error_handling",
                    "title": "Missing error handling",
                    "explanation": "No try/catch block",
                    "suggested_fix": "Add try/catch"
                }
            ]
        }
        
        result = build_initial_review_comment(issues_by_severity, 2, "Found 2 issues")
        
        assert "CRITICAL" in result
        assert "MAJOR" in result
        assert "SQL injection" in result
        assert "Missing error handling" in result
