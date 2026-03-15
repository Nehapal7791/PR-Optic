"""
Anthropic Claude AI Provider

Refactored from claude_service.py to implement the AIProvider interface.
"""

import json
import re
from anthropic import Anthropic
from src.config import settings
from src.utils.logger import get_logger
from src.models.github import PRFile
from src.models.review import (
    TriageResult,
    ReviewResult,
    ReviewComment,
    ConcernCategory,
    ReviewScore,
    Severity
)
from src.exceptions import ClaudeServiceError
from src.services.ai_provider import AIProvider

logger = get_logger(__name__)


class ClaudeProvider(AIProvider):
    """Anthropic Claude AI provider for code review."""
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self._max_tokens = 4000
        logger.info(f"ClaudeProvider initialized with max_tokens={self._max_tokens}")
    
    @property
    def provider_name(self) -> str:
        return "claude"
    
    @property
    def max_tokens(self) -> int:
        return self._max_tokens
    
    def _extract_json_from_response(self, text: str) -> dict:
        """Extract JSON from Claude response, handling markdown fences."""
        # Try to find JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'{.*}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ClaudeServiceError(f"No JSON found in response: {text[:200]}")
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}\nJSON string: {json_str[:500]}")
            raise ClaudeServiceError(f"Invalid JSON in response: {e}")
    
    async def triage_diff(
        self,
        files: list[PRFile],
        pr_title: str,
        pr_body: str | None
    ) -> TriageResult:
        """First pass: Classify diff into concern categories."""
        logger.info(f"Triaging diff with {len(files)} files using Claude")
        
        # Handle empty files list
        if not files:
            logger.info("No files to triage, returning empty categories")
            return TriageResult(
                categories=[],
                reasoning="No files changed in this PR"
            )
        
        # Build diff summary
        diff_summary = f"PR Title: {pr_title}\n"
        if pr_body:
            diff_summary += f"PR Description: {pr_body[:500]}\n\n"
        
        diff_summary += "Files changed:\n"
        for file in files[:20]:  # Limit to first 20 files
            diff_summary += f"\n--- {file.filename} (+{file.additions} -{file.deletions})\n"
            if file.patch:
                diff_summary += file.patch[:1000]  # Limit patch size
        
        triage_prompt = f"""You are a senior software engineer performing code review triage.

Analyze this pull request and identify which concern categories apply.

Available categories:
- hardcoded_values: Hardcoded secrets, URLs, magic numbers
- reusability: Code duplication, missing abstractions
- logic_errors: Bugs, edge cases, incorrect logic
- security: Security vulnerabilities, unsafe operations
- maintainability: Complex code, poor structure
- env_config: Environment variable misuse
- missing_abstractions: Lack of proper abstractions

Diff:
{diff_summary}

Respond with JSON only:
{{
  "categories": ["category1", "category2"],
  "reasoning": "Brief explanation of why these categories apply"
}}

Only include categories that have genuine concerns. If the PR looks good, return empty categories array."""
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=self._max_tokens,
                messages=[{
                    "role": "user",
                    "content": triage_prompt
                }]
            )
            
            response_text = response.content[0].text
            logger.debug(f"Triage response: {response_text[:500]}")
            
            data = self._extract_json_from_response(response_text)
            
            # Validate and convert categories
            categories = []
            for cat_str in data.get("categories", []):
                try:
                    categories.append(ConcernCategory(cat_str))
                except ValueError:
                    logger.warning(f"Unknown category: {cat_str}")
            
            result = TriageResult(
                categories=categories,
                reasoning=data.get("reasoning", "")
            )
            
            logger.info(f"Triage complete: {len(result.categories)} categories identified")
            return result
        
        except Exception as e:
            logger.error(f"Triage failed: {e}", exc_info=True)
            raise ClaudeServiceError(f"Triage failed: {e}")
    
    async def review_pull_request(
        self,
        files: list[PRFile],
        pr_title: str,
        pr_body: str | None,
        categories: list[ConcernCategory]
    ) -> ReviewResult:
        """Second pass: Focused review per identified category."""
        logger.info(f"Reviewing PR with {len(categories)} categories using Claude")
        
        # Handle empty files or no categories
        if not files or not categories:
            logger.info("No files or categories, returning approve with no comments")
            return ReviewResult(
                summary="No significant concerns found. Code looks good!",
                score=ReviewScore.APPROVE,
                comments=[],
                categories_reviewed=[]
            )
        
        # Build full diff
        full_diff = f"PR Title: {pr_title}\n"
        if pr_body:
            full_diff += f"PR Description: {pr_body[:500]}\n\n"
        
        full_diff += "Files changed:\n"
        for file in files[:20]:  # Limit to first 20 files
            full_diff += f"\n--- {file.filename} (+{file.additions} -{file.deletions})\n"
            if file.patch:
                full_diff += file.patch[:2000]  # Limit patch size
        
        categories_str = ", ".join([c.value for c in categories])
        
        review_prompt = f"""You are a senior software engineer conducting a code review.

Your tone should be:
- Constructive and helpful
- Explain WHY, not just WHAT
- Focus on production-readiness
- Group comments by functionality/module

Focus ONLY on these concern categories: {categories_str}

EXPLICITLY CHECK FOR:
- Hardcoded values (secrets, URLs, magic numbers)
- Environment config misuse
- Code reusability and abstractions
- Missing error handling
- Security vulnerabilities
- Logic errors and edge cases

EXPLICITLY SKIP:
- Formatting and whitespace
- Naming conventions (unless truly confusing)
- Style preferences

Diff:
{full_diff}

Provide max 10 comments, grouped by functionality.

Respond with JSON only:
{{
  "summary": "Overall assessment",
  "score": "approve" | "comment" | "request_changes",
  "comments": [
    {{
      "filename": "path/to/file.py",
      "line": 42,
      "category": "hardcoded_values",
      "severity": "critical" | "major" | "minor" | "info",
      "body": "Explanation of the issue and WHY it matters",
      "suggested_fix": "Optional code suggestion"
    }}
  ]
}}

If no issues found, return score="approve" with empty comments array."""
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=self._max_tokens,
                messages=[{
                    "role": "user",
                    "content": review_prompt
                }]
            )
            
            response_text = response.content[0].text
            logger.debug(f"Review response: {response_text[:500]}")
            
            data = self._extract_json_from_response(response_text)
            
            # Parse comments
            comments = []
            for comment_data in data.get("comments", [])[:10]:  # Max 10
                try:
                    comment = ReviewComment(
                        filename=comment_data["filename"],
                        line=max(1, comment_data.get("line", 1)),  # Ensure line > 0
                        category=ConcernCategory(comment_data["category"]),
                        severity=Severity(comment_data.get("severity", "info")),
                        body=comment_data["body"],
                        suggested_fix=comment_data.get("suggested_fix")
                    )
                    comments.append(comment)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping invalid comment: {e}")
            
            # Parse score
            score_str = data.get("score", "comment")
            try:
                score = ReviewScore(score_str)
            except ValueError:
                logger.warning(f"Invalid score '{score_str}', defaulting to COMMENT")
                score = ReviewScore.COMMENT
            
            result = ReviewResult(
                summary=data.get("summary", "Review complete"),
                score=score,
                comments=comments,
                categories_reviewed=categories
            )
            
            logger.info(f"Review complete: {score.value}, {len(comments)} comments")
            return result
        
        except Exception as e:
            logger.error(f"Review failed: {e}", exc_info=True)
            raise ClaudeServiceError(f"Review failed: {e}")
