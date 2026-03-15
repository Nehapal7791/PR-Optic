"""
Review Orchestrator - Agent-Aware Pipeline with State Routing

The core routing brain that decides between fresh review and fix verification.
"""

import time
from datetime import datetime
from src.services.github_service import GitHubService
from src.services.claude_service import ClaudeService
from src.services.state_service import StateService
from src.models.review import ReviewResult, ReviewScore, ReviewComment
from src.models.state import VerificationResult, IssueVerification
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReviewOrchestrator:
    """Orchestrates PR reviews with state-aware routing."""
    
    def __init__(
        self,
        github_service: GitHubService | None = None,
        ai_service: ClaudeService | None = None,
        state_service: StateService | None = None
    ):
        """Initialize orchestrator.
        
        Args:
            github_service: GitHub API service
            ai_service: AI review service
            state_service: State persistence service
        """
        self.github = github_service or GitHubService()
        self.ai = ai_service or ClaudeService()
        self.state = state_service or StateService()
        
        logger.info(f"ReviewOrchestrator initialized with AI provider: {self.ai._provider.provider_name}")
    
    def _log_step(self, step: str, message: str):
        """Log a step with timestamp.
        
        Args:
            step: Step name
            message: Log message
        """
        from datetime import timezone
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{timestamp}] STEP {step}: {message}")
        print(f"[{timestamp}] STEP {step}: {message}")
    
    async def orchestrate(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        post_to_github: bool = True
    ) -> ReviewResult | VerificationResult:
        """Main orchestration entry point with state-aware routing.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: Commit SHA to review
            post_to_github: Whether to post results to GitHub (False for dashboard mode)
        
        Returns:
            ReviewResult for fresh review or VerificationResult for re-review
        """
        pr_id = f"{owner}/{repo}/{pull_number}"
        
        self._log_step("0", f"Starting orchestration for PR {pr_id} @ {commit_sha[:8]}")
        
        # Step 0: Check state store
        self._log_step("0.1", "Checking state store for existing review")
        existing_state = self.state.load(pr_id)
        
        if existing_state and existing_state.open_issues:
            # Route to verify_fixes
            self._log_step("0.2", f"Found {len(existing_state.open_issues)} open issues - routing to verify_fixes()")
            return await self.verify_fixes(
                owner, repo, pull_number, commit_sha,
                existing_state, post_to_github
            )
        else:
            # Route to run_review
            self._log_step("0.2", "New PR or no open issues - routing to run_review()")
            return await self.run_review(
                owner, repo, pull_number, commit_sha,
                post_to_github
            )
    
    async def run_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        post_to_github: bool = True
    ) -> ReviewResult:
        """Run fresh PR review.
        
        Steps:
        1. Fetch PR details and files
        2. Filter files (skip generated, large files)
        3. Triage - identify concern categories
        4. Focused review - generate comments per category
        5. Post comments to GitHub (if post_to_github=True)
        6. Save state with open issues
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: Commit SHA to review
            post_to_github: Whether to post to GitHub
        
        Returns:
            ReviewResult
        """
        pr_id = f"{owner}/{repo}/{pull_number}"
        start_time = time.time()
        
        try:
            # Step 1: Fetch PR data
            self._log_step("1", f"Fetching PR details for {pr_id}")
            pr = await self.github.get_pr_details(owner, repo, pull_number)
            
            self._log_step("1.1", f"Fetching changed files")
            files = await self.github.get_pr_files(owner, repo, pull_number)
            
            # Step 1.2: Early return for empty files
            if not files:
                self._log_step("1.2", "No files changed - returning early with APPROVE")
                result = ReviewResult(
                    summary="No files changed in this PR",
                    score=ReviewScore.APPROVE,
                    comments=[],
                    categories_reviewed=[]
                )
                return result
            
            self._log_step("1.2", f"Found {len(files)} changed files")
            
            # Step 2: Filter files
            self._log_step("2", "Filtering files (skip generated, large files)")
            filtered_files = self._filter_files(files)
            self._log_step("2.1", f"Filtered to {len(filtered_files)} reviewable files")
            
            if not filtered_files:
                self._log_step("2.2", "No reviewable files - returning early with APPROVE")
                result = ReviewResult(
                    summary="No reviewable files (all generated or too large)",
                    score=ReviewScore.APPROVE,
                    comments=[],
                    categories_reviewed=[]
                )
                return result
            
            # Step 3: Triage
            self._log_step("3", "Running triage to identify concern categories")
            triage_result = await self.ai.triage_diff(
                files=filtered_files,
                pr_title=pr.title,
                pr_body=pr.body
            )
            self._log_step("3.1", f"Triage identified {len(triage_result.categories)} categories: {[c.value for c in triage_result.categories]}")
            
            # Step 4: Focused review
            self._log_step("4", "Running focused review")
            review_result = await self.ai.review_pull_request(
                files=filtered_files,
                pr_title=pr.title,
                pr_body=pr.body,
                categories=triage_result.categories
            )
            self._log_step("4.1", f"Review complete: {review_result.score.value}, {len(review_result.comments)} comments")
            
            # Step 5: Post to GitHub
            if post_to_github and review_result.comments:
                self._log_step("5", f"Posting {len(review_result.comments)} comments to GitHub")
                await self._post_review_to_github(
                    owner, repo, pull_number, commit_sha, review_result
                )
                self._log_step("5.1", "Comments posted successfully")
            elif not post_to_github:
                self._log_step("5", "Skipping GitHub post (post_to_github=False)")
            else:
                self._log_step("5", "No comments to post")
            
            # Step 6: Save state
            self._log_step("6", "Saving review state")
            self.state.save(pr_id, commit_sha, review_result)
            self._log_step("6.1", "State saved successfully")
            
            elapsed = time.time() - start_time
            self._log_step("DONE", f"Review complete in {elapsed:.2f}s")
            
            return review_result
            
        except Exception as e:
            self._log_step("ERROR", f"Review failed: {e}")
            logger.error(f"Review failed for {pr_id}: {e}", exc_info=True)
            
            # Return partial result on failure
            return ReviewResult(
                summary=f"Review failed: {str(e)}",
                score=ReviewScore.COMMENT,
                comments=[],
                categories_reviewed=[]
            )
    
    async def verify_fixes(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        existing_state,
        post_to_github: bool = True
    ) -> VerificationResult:
        """Verify fixes for previously identified issues.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: New commit SHA to verify
            existing_state: Previous review state
            post_to_github: Whether to post to GitHub
        
        Returns:
            VerificationResult
        """
        pr_id = f"{owner}/{repo}/{pull_number}"
        start_time = time.time()
        
        try:
            self._log_step("V1", f"Verifying fixes for {len(existing_state.open_issues)} open issues")
            
            # Fetch new files
            self._log_step("V2", "Fetching current PR files")
            files = await self.github.get_pr_files(owner, repo, pull_number)
            
            # Verify each issue
            verifications = []
            fixed_count = 0
            
            for i, issue in enumerate(existing_state.open_issues, 1):
                self._log_step(f"V3.{i}", f"Verifying issue: {issue.filename}:{issue.line}")
                
                # Find relevant file
                relevant_file = next(
                    (f for f in files if f.filename == issue.filename),
                    None
                )
                
                if not relevant_file:
                    # File removed or renamed - consider fixed
                    verification = IssueVerification(
                        issue_id=issue.issue_id,
                        is_fixed=True,
                        verification_comment="File no longer present in PR",
                        confidence=0.9
                    )
                    fixed_count += 1
                else:
                    # Ask AI to verify fix
                    verification = await self._verify_single_issue(issue, relevant_file)
                    if verification.is_fixed:
                        fixed_count += 1
                
                verifications.append(verification)
                self._log_step(f"V3.{i}.1", f"Issue {'FIXED' if verification.is_fixed else 'STILL OPEN'}")
            
            # Create result
            all_fixed = fixed_count == len(existing_state.open_issues)
            
            result = VerificationResult(
                pr_id=pr_id,
                commit_sha=commit_sha,
                total_issues=len(existing_state.open_issues),
                fixed_issues=fixed_count,
                still_open_issues=len(existing_state.open_issues) - fixed_count,
                verifications=verifications,
                summary=self._create_verification_summary(verifications),
                all_fixed=all_fixed
            )
            
            self._log_step("V4", f"Verification complete: {fixed_count}/{len(existing_state.open_issues)} fixed")
            
            # Update state
            if all_fixed:
                self._log_step("V5", "All issues fixed - clearing state")
                self.state.clear(pr_id)
            else:
                # Update state with remaining issues
                still_open = [
                    issue for issue, ver in zip(existing_state.open_issues, verifications)
                    if not ver.is_fixed
                ]
                self._log_step("V5", f"Updating state with {len(still_open)} remaining issues")
                # TODO: Update state with remaining issues
            
            # Post to GitHub if requested
            if post_to_github:
                self._log_step("V6", "Posting verification result to GitHub")
                await self._post_verification_to_github(
                    owner, repo, pull_number, commit_sha, result
                )
            
            elapsed = time.time() - start_time
            self._log_step("DONE", f"Verification complete in {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            self._log_step("ERROR", f"Verification failed: {e}")
            logger.error(f"Verification failed for {pr_id}: {e}", exc_info=True)
            raise
    
    def _filter_files(self, files):
        """Filter out generated files and very large files.
        
        Args:
            files: List of PRFile objects
        
        Returns:
            Filtered list of files
        """
        filtered = []
        
        for file in files:
            # Skip generated files
            if any(pattern in file.filename.lower() for pattern in [
                'package-lock.json', 'yarn.lock', 'poetry.lock',
                '.min.js', '.min.css', 'dist/', 'build/',
                '__pycache__', '.pyc', 'node_modules/'
            ]):
                logger.debug(f"Skipping generated file: {file.filename}")
                continue
            
            # Skip very large files (>500 changes)
            if file.changes > 500:
                logger.debug(f"Skipping large file: {file.filename} ({file.changes} changes)")
                continue
            
            filtered.append(file)
        
        return filtered
    
    async def _verify_single_issue(self, issue, file):
        """Verify if a single issue has been fixed.
        
        Args:
            issue: OpenIssue to verify
            file: Current PRFile
        
        Returns:
            IssueVerification
        """
        # Simple heuristic for now - check if the problematic line changed
        # In future, ask AI to verify
        
        if not file.patch:
            return IssueVerification(
                issue_id=issue.issue_id,
                is_fixed=False,
                verification_comment="No patch available to verify",
                confidence=0.5
            )
        
        # Check if line appears in patch
        lines_in_patch = set()
        for line in file.patch.split('\n'):
            if line.startswith('@@'):
                # Parse line numbers from hunk header
                # Format: @@ -old_start,old_count +new_start,new_count @@
                parts = line.split()
                if len(parts) >= 3:
                    new_range = parts[2]  # +new_start,new_count
                    if ',' in new_range:
                        start = int(new_range.split(',')[0].lstrip('+'))
                        count = int(new_range.split(',')[1])
                        lines_in_patch.update(range(start, start + count))
        
        if issue.line in lines_in_patch:
            return IssueVerification(
                issue_id=issue.issue_id,
                is_fixed=True,
                verification_comment=f"Line {issue.line} was modified in this commit",
                confidence=0.7
            )
        else:
            return IssueVerification(
                issue_id=issue.issue_id,
                is_fixed=False,
                verification_comment=f"Line {issue.line} was not modified",
                confidence=0.8
            )
    
    def _create_verification_summary(self, verifications):
        """Create summary text for verification result.
        
        Args:
            verifications: List of IssueVerification
        
        Returns:
            Summary string
        """
        fixed = sum(1 for v in verifications if v.is_fixed)
        total = len(verifications)
        
        if fixed == total:
            return f"✅ All {total} issues have been fixed!"
        elif fixed == 0:
            return f"❌ None of the {total} issues have been fixed yet"
        else:
            return f"⚠️ {fixed}/{total} issues fixed, {total - fixed} still open"
    
    def _format_comment_body(self, comment: ReviewComment) -> str:
        """Format a single comment body with PR-Optic branding.
        
        Args:
            comment: Review comment to format
            
        Returns:
            Formatted comment body
        """
        severity_emoji = {
            "critical": "🔴",
            "major": "🟠",
            "minor": "🟡"
        }.get(comment.severity.value, "⚪")
        
        body = f"{severity_emoji} **[{comment.severity.value.upper()}] {comment.category.value}**\n\n"
        body += f"{comment.body}\n\n"
        
        if comment.suggested_fix:
            body += f"**💡 Suggested fix:**\n```\n{comment.suggested_fix}\n```\n\n"
        
        body += "---\n*🤖 AI Code Review by [PR-Optic](https://github.com/Nehapal7791/PR-Optic)*"
        
        return body
    
    async def _post_individual_comments(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        comments: list[ReviewComment]
    ) -> tuple[int, int]:
        """Post individual inline comments on PR.
        
        Posts each comment separately like a senior developer would,
        with each issue as its own comment thread.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: Commit SHA
            comments: List of review comments
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        successful = 0
        failed = 0
        
        for comment in comments:
            try:
                formatted_body = self._format_comment_body(comment)
                
                await self.github.post_pr_comment(
                    owner=owner,
                    repo=repo,
                    pr_number=pull_number,
                    commit_sha=commit_sha,
                    path=comment.filename,
                    line=comment.line,
                    body=formatted_body,
                    side="RIGHT"
                )
                successful += 1
                self._log_step("COMMENT", f"Posted comment on {comment.filename}:{comment.line}")
                
            except Exception as e:
                failed += 1
                logger.warning(f"Failed to post comment on {comment.filename}:{comment.line}: {e}")
                continue
        
        return successful, failed
    
    async def _post_review_summary(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        review_result: ReviewResult,
        comments_posted: int
    ):
        """Post overall review summary.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: Commit SHA
            review_result: Review result
            comments_posted: Number of individual comments posted
        """
        body = f"## 🤖 AI Code Review by PR-Optic\n\n"
        body += f"{review_result.summary}\n\n"
        
        if comments_posted > 0:
            body += f"📝 **{comments_posted} inline comments** posted on specific lines.\n\n"
        
        body += "---\n*Powered by [PR-Optic](https://github.com/Nehapal7791/PR-Optic) - AI-powered code review assistant*"
        
        event_map = {
            ReviewScore.APPROVE: "APPROVE",
            ReviewScore.REQUEST_CHANGES: "REQUEST_CHANGES",
            ReviewScore.COMMENT: "COMMENT"
        }
        
        await self.github.post_review(
            owner=owner,
            repo=repo,
            pr_number=pull_number,
            commit_sha=commit_sha,
            body=body,
            event=event_map[review_result.score],
            comments=None
        )
    
    async def _post_review_to_github(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        review_result: ReviewResult
    ):
        """Post review result to GitHub as individual comments.
        
        Posts each issue as a separate inline comment, similar to how
        senior developers review code.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: Commit SHA
            review_result: Review result to post
        """
        # Post individual inline comments
        successful, failed = await self._post_individual_comments(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            commit_sha=commit_sha,
            comments=review_result.comments
        )
        
        self._log_step("5.1", f"Posted {successful} inline comments ({failed} failed)")
        
        # Post overall review summary
        await self._post_review_summary(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            commit_sha=commit_sha,
            review_result=review_result,
            comments_posted=successful
        )
    
    async def _post_verification_to_github(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        verification_result: VerificationResult
    ):
        """Post verification result to GitHub.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pull_number: Pull request number
            commit_sha: Commit SHA
            verification_result: Verification result to post
        """
        # Create summary comment
        body = f"## 🔍 Fix Verification Results\n\n{verification_result.summary}\n\n"
        
        if verification_result.all_fixed:
            body += "All previously identified issues have been addressed. Great work! 🎉"
            event = "APPROVE"
        else:
            body += "### Still Open Issues:\n\n"
            for ver in verification_result.verifications:
                if not ver.is_fixed:
                    body += f"- {ver.issue_id}: {ver.verification_comment}\n"
            event = "COMMENT"
        
        await self.github.post_review(
            owner=owner,
            repo=repo,
            pr_number=pull_number,
            commit_sha=commit_sha,
            body=body,
            event=event,
            comments=None
        )
