"""
Fix Verifier Service - The Re-Review Loop Brain

This is the core of the agent loop. It makes the bot a true agent:
- Memory: Loads previous issues from state store
- Perception: Fetches new commit diff
- Reasoning: Calls Claude to verify if fixes are sufficient
- Action: Updates state and posts approve/request-changes review
"""

import json
from collections import defaultdict
from src.models.state import OpenIssue, IssueVerification, VerificationResult
from src.models.review import ReviewScore
from src.services.sqlite_state_service import SQLiteStateService
from src.services.github_service import GitHubService
from src.services.providers.claude_provider import ClaudeProvider
from src.utils.logger import get_logger
from src.utils.step_logger import StepLogger
from src.prompts.senior_review import build_verification_prompt

logger = get_logger(__name__)


class FixVerifierService:
    """Service for verifying developer fixes in re-review loops.
    
    This is the agent's brain - it perceives changes, reasons about fixes,
    and decides whether to approve or request more changes.
    """
    
    def __init__(
        self,
        state_service: SQLiteStateService,
        github_service: GitHubService,
        claude_provider: ClaudeProvider
    ):
        """Initialize fix verifier service.
        
        Args:
            state_service: State store for agent memory
            github_service: GitHub API client
            claude_provider: Claude AI provider
        """
        self.state_service = state_service
        self.github_service = github_service
        self.claude_provider = claude_provider
        logger.info("FixVerifierService initialized")
    
    async def verify_fixes(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        new_commit_sha: str
    ) -> VerificationResult:
        """Verify if developer fixed the issues we raised.
        
        This is the core agent loop:
        1. Load open issues from memory (state store)
        2. Fetch new commit diff (perception)
        3. Ask Claude if fixes are sufficient (reasoning)
        4. Update state and post review (action)
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: PR number
            new_commit_sha: New commit SHA to verify
            
        Returns:
            VerificationResult with verification details
        """
        pr_id = f"{owner}/{repo}/{pull_number}"
        step_logger = StepLogger(pr_id=pr_id, operation="verify_fixes")
        
        step_logger.log_step("Loading previous state from memory")
        
        # Load state from memory
        state = self.state_service.load(pr_id)
        
        if not state:
            logger.warning(f"No previous state found for {pr_id} - cannot verify fixes")
            return VerificationResult(
                pr_id=pr_id,
                commit_sha=new_commit_sha,
                total_issues=0,
                fixed_issues=0,
                still_open_issues=0,
                verifications=[],
                summary="No previous review found - cannot verify fixes",
                all_fixed=False
            )
        
        # Check if already verified this commit
        if state.last_reviewed_commit == new_commit_sha:
            logger.info(f"Commit {new_commit_sha[:7]} already verified - skipping")
            step_logger.log_step("Commit already verified - skipping", {
                "commit_sha": new_commit_sha[:7]
            })
            
            return VerificationResult(
                pr_id=pr_id,
                commit_sha=new_commit_sha,
                total_issues=len(state.all_issues),
                fixed_issues=len(state.resolved_issues),
                still_open_issues=len([i for i in state.all_issues if not i.resolved]),
                verifications=[],
                summary=f"Already verified commit {new_commit_sha[:7]}",
                all_fixed=all([i.resolved for i in state.all_issues])
            )
        
        # Get open issues
        open_issues = [issue for issue in state.all_issues if not issue.resolved]
        
        if not open_issues:
            logger.info(f"No open issues for {pr_id} - all already resolved")
            step_logger.log_completion("No open issues to verify")
            
            return VerificationResult(
                pr_id=pr_id,
                commit_sha=new_commit_sha,
                total_issues=len(state.all_issues),
                fixed_issues=len(state.all_issues),
                still_open_issues=0,
                verifications=[],
                summary="All issues already resolved",
                all_fixed=True
            )
        
        step_logger.log_step("Fetching commit diff from GitHub", {
            "commit_sha": new_commit_sha[:7],
            "open_issues": len(open_issues)
        })
        
        # Fetch commit diff
        try:
            commit_diff = await self.github_service.get_commit_diff(
                owner=owner,
                repo=repo,
                commit_sha=new_commit_sha
            )
        except Exception as e:
            logger.error(f"Failed to fetch commit diff: {e}", exc_info=True)
            raise
        
        step_logger.log_step("Grouping issues by category for efficient verification")
        
        # Group issues by category (one Claude call per category)
        issues_by_category = self._group_issues_by_category(open_issues)
        
        logger.info(
            f"Verifying {len(open_issues)} issues across "
            f"{len(issues_by_category)} categories"
        )
        
        # Verify each category
        all_verifications = []
        
        for category, category_issues in issues_by_category.items():
            step_logger.log_step(
                f"Verifying {category} issues with Claude",
                {"issue_count": len(category_issues)}
            )
            
            verifications = await self._verify_category_issues(
                category=category,
                issues=category_issues,
                commit_diff=commit_diff,
                pr_id=pr_id
            )
            
            all_verifications.extend(verifications)
        
        step_logger.log_step("Updating state store with verification results")
        
        # Update state store
        fixed_count = 0
        for verification in all_verifications:
            if verification.is_fixed:
                self.state_service.update_issue(
                    pr_id=pr_id,
                    issue_id=verification.issue_id,
                    resolved=True
                )
                fixed_count += 1
        
        # Increment round
        new_round = state.round + 1
        
        # Reload state to get updated data
        updated_state = self.state_service.load(pr_id)
        still_open = [i for i in updated_state.all_issues if not i.resolved]
        
        all_fixed = len(still_open) == 0
        
        # Build result
        result = VerificationResult(
            pr_id=pr_id,
            commit_sha=new_commit_sha,
            total_issues=len(open_issues),
            fixed_issues=fixed_count,
            still_open_issues=len(still_open),
            verifications=all_verifications,
            summary=self._build_summary(fixed_count, len(still_open), all_fixed),
            all_fixed=all_fixed
        )
        
        step_logger.log_step("Posting review to GitHub", {
            "verdict": "APPROVE" if all_fixed else "REQUEST_CHANGES",
            "fixed": fixed_count,
            "still_open": len(still_open)
        })
        
        # Post review to GitHub
        await self._post_verification_review(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            commit_sha=new_commit_sha,
            result=result,
            still_open_issues=still_open
        )
        
        # Save updated round number and commit SHA
        self.state_service.save(
            pr_id=pr_id,
            issues=updated_state.all_issues,
            commit_sha=new_commit_sha,
            score=ReviewScore.APPROVE if all_fixed else ReviewScore.REQUEST_CHANGES,
            summary=result.summary,
            round_num=new_round
        )
        
        # Mark as approved if all fixed
        if all_fixed:
            self.state_service.mark_approved(pr_id)
        
        step_logger.log_completion(
            f"Verified {fixed_count}/{len(open_issues)} issues fixed"
        )
        
        return result
    
    def _group_issues_by_category(
        self,
        issues: list[OpenIssue]
    ) -> dict[str, list[OpenIssue]]:
        """Group issues by category for batch verification.
        
        Args:
            issues: List of issues to group
            
        Returns:
            Dict mapping category to list of issues
        """
        grouped = defaultdict(list)
        for issue in issues:
            grouped[issue.category].append(issue)
        return dict(grouped)
    
    async def _verify_category_issues(
        self,
        category: str,
        issues: list[OpenIssue],
        commit_diff: str,
        pr_id: str
    ) -> list[IssueVerification]:
        """Verify all issues in a category with one Claude call.
        
        Args:
            category: Issue category
            issues: Issues in this category
            commit_diff: Commit diff to analyze
            pr_id: PR identifier for logging
            
        Returns:
            List of issue verifications
        """
        # Build verification prompt from library
        prompts = build_verification_prompt(
            issues=issues,
            new_diff=commit_diff,
            category=category
        )
        
        # Call Claude
        try:
            response = await self.claude_provider.generate(
                prompt=prompts["user"],
                system_prompt=prompts["system"]
            )
            
            # Parse JSON response
            verifications = self._parse_verification_response(response, issues)
            
            logger.info(
                f"Verified {len(verifications)} {category} issues for {pr_id}"
            )
            
            return verifications
            
        except Exception as e:
            logger.error(
                f"Failed to verify {category} issues: {e}",
                exc_info=True
            )
            
            # Return conservative verifications (assume not fixed)
            return [
                IssueVerification(
                    issue_id=issue.id,
                    is_fixed=False,
                    verification_comment=f"Verification failed: {str(e)}",
                    confidence=0.0
                )
                for issue in issues
            ]
    
    
    def _parse_verification_response(
        self,
        response: str,
        issues: list[OpenIssue]
    ) -> list[IssueVerification]:
        """Parse Claude's verification response.
        
        Args:
            response: Claude's JSON response
            issues: Original issues
            
        Returns:
            List of issue verifications
        """
        try:
            # Extract JSON from response
            response = response.strip()
            
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            data = json.loads(response)
            
            verifications = []
            for item in data.get("verifications", []):
                verifications.append(
                    IssueVerification(
                        issue_id=item["issue_id"],
                        is_fixed=item["is_fixed"],
                        verification_comment=item["comment"],
                        confidence=item.get("confidence", 0.8)
                    )
                )
            
            # Ensure we have verification for each issue
            verified_ids = {v.issue_id for v in verifications}
            for issue in issues:
                if issue.id not in verified_ids:
                    logger.warning(f"No verification for issue {issue.id} - assuming not fixed")
                    verifications.append(
                        IssueVerification(
                            issue_id=issue.id,
                            is_fixed=False,
                            verification_comment="No verification provided by AI",
                            confidence=0.5
                        )
                    )
            
            return verifications
            
        except Exception as e:
            logger.error(f"Failed to parse verification response: {e}", exc_info=True)
            logger.debug(f"Response was: {response}")
            
            # Return conservative verifications
            return [
                IssueVerification(
                    issue_id=issue.id,
                    is_fixed=False,
                    verification_comment=f"Failed to parse verification: {str(e)}",
                    confidence=0.0
                )
                for issue in issues
            ]
    
    def _build_summary(
        self,
        fixed_count: int,
        still_open_count: int,
        all_fixed: bool
    ) -> str:
        """Build verification summary message.
        
        Args:
            fixed_count: Number of issues fixed
            still_open_count: Number of issues still open
            all_fixed: Whether all issues are fixed
            
        Returns:
            Summary message
        """
        if all_fixed:
            return (
                f"🎉 Excellent work! All {fixed_count} issue(s) have been "
                f"successfully resolved. The code is ready to merge."
            )
        elif fixed_count > 0:
            return (
                f"✅ Good progress! Fixed {fixed_count} issue(s), but "
                f"{still_open_count} issue(s) still need attention."
            )
        else:
            return (
                f"⚠️ The issues raised in the previous review have not been "
                f"addressed yet. Please review the feedback and make the "
                f"necessary changes."
            )
    
    async def _post_verification_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        result: VerificationResult,
        still_open_issues: list[OpenIssue]
    ) -> None:
        """Post verification review to GitHub.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: PR number
            commit_sha: Commit SHA
            result: Verification result
            still_open_issues: Issues that are still open
        """
        # Build review body
        body_parts = [
            "## 🔄 Re-Review Results\n",
            result.summary,
            "\n### Verification Summary\n",
            f"- **Total issues checked:** {result.total_issues}",
            f"- **Issues fixed:** {result.fixed_issues} ✅",
            f"- **Issues remaining:** {result.still_open_issues} ⚠️",
        ]
        
        if result.fixed_issues > 0:
            body_parts.append("\n### ✅ Fixed Issues\n")
            for verification in result.verifications:
                if verification.is_fixed:
                    body_parts.append(
                        f"- **{verification.issue_id}**: {verification.verification_comment}"
                    )
        
        if still_open_issues:
            body_parts.append("\n### ⚠️ Issues Still Open\n")
            for issue in still_open_issues:
                verification = next(
                    (v for v in result.verifications if v.issue_id == issue.id),
                    None
                )
                comment = verification.verification_comment if verification else "Not yet addressed"
                body_parts.append(
                    f"- **{issue.file}:{issue.line}** ({issue.category}): {issue.body}\n"
                    f"  *Verification:* {comment}"
                )
        
        body = "\n".join(body_parts)
        
        # Determine event
        event = "APPROVE" if result.all_fixed else "REQUEST_CHANGES"
        
        # Post review
        try:
            await self.github_service.post_review(
                owner=owner,
                repo=repo,
                pull_number=pull_number,
                commit_sha=commit_sha,
                body=body,
                event=event
            )
            
            logger.info(
                f"Posted {event} review for PR {owner}/{repo}/{pull_number}"
            )
            
        except Exception as e:
            logger.error(f"Failed to post verification review: {e}", exc_info=True)
            raise
