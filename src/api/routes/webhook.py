"""GitHub Webhook Receiver - Smart Routing for New PR vs Fix Commit"""

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from src.services.webhook_security import verify_github_signature, WebhookSecurityError
from src.services.review_orchestrator import ReviewOrchestrator
from src.services.state_service import StateService
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["webhook"])


class WebhookRouter:
    """Routes webhook events to appropriate handlers based on PR state."""
    
    def __init__(self):
        self.orchestrator = ReviewOrchestrator()
        self.state_service = StateService()
    
    def _log_routing_decision(self, decision: str, pr_id: str, action: str):
        """Log routing decision for debugging and audit.
        
        Args:
            decision: Routing decision (NEW_PR, FIX_COMMIT, SKIP)
            pr_id: PR identifier (owner/repo/number)
            action: GitHub action that triggered the event
        """
        logger.info(f"🔀 ROUTING: {decision} → {action} | PR: {pr_id}")
    
    async def route_pull_request_event(
        self,
        action: str,
        pull_request: dict,
        repository: dict
    ):
        """Route pull request event to appropriate handler.
        
        Smart routing logic:
        - action: opened → NEW_PR → run_review()
        - action: synchronize + state exists → FIX_COMMIT → verify_fixes()
        - action: synchronize + no state → NEW_PR → run_review()
        - other actions → SKIP
        
        Args:
            action: GitHub action (opened, synchronize, etc.)
            pull_request: PR data from webhook
            repository: Repository data from webhook
        """
        owner = repository["owner"]["login"]
        repo = repository["name"]
        pr_number = pull_request["number"]
        commit_sha = pull_request["head"]["sha"]
        pr_id = f"{owner}/{repo}/{pr_number}"
        
        logger.info(f"📥 Processing PR event: {action} | {pr_id} @ {commit_sha[:8]}")
        
        # Route based on action and state
        if action == "opened":
            # New PR - always run fresh review
            self._log_routing_decision("NEW_PR", pr_id, "run_review()")
            
            await self.orchestrator.orchestrate(
                owner=owner,
                repo=repo,
                pull_number=pr_number,
                commit_sha=commit_sha,
                post_to_github=True
            )
        
        elif action == "synchronize":
            # New commit on existing PR - check state to decide
            existing_state = self.state_service.load(pr_id)
            
            if existing_state and len(existing_state.open_issues) > 0:
                # PR has open issues - verify fixes
                self._log_routing_decision("FIX_COMMIT", pr_id, "verify_fixes()")
                
                await self.orchestrator.orchestrate(
                    owner=owner,
                    repo=repo,
                    pull_number=pr_number,
                    commit_sha=commit_sha,
                    post_to_github=True
                )
            else:
                # No state or no open issues - treat as new review
                self._log_routing_decision("NEW_PR", pr_id, "run_review() [first review or all fixed]")
                
                await self.orchestrator.orchestrate(
                    owner=owner,
                    repo=repo,
                    pull_number=pr_number,
                    commit_sha=commit_sha,
                    post_to_github=True
                )
        
        else:
            # Other actions (closed, edited, etc.) - skip processing
            self._log_routing_decision("SKIP", pr_id, f"action={action} [not processed]")
            logger.info(f"⏭️  Skipping action: {action}")


# Global router instance
webhook_router = WebhookRouter()


async def process_webhook_background(event_type: str, payload: dict):
    """Process webhook in background to return 200 immediately.
    
    Args:
        event_type: GitHub event type (pull_request, ping, etc.)
        payload: Webhook payload
    """
    try:
        if event_type == "pull_request":
            action = payload.get("action")
            pull_request = payload.get("pull_request")
            repository = payload.get("repository")
            
            if not all([action, pull_request, repository]):
                logger.error("Missing required fields in pull_request event")
                return
            
            await webhook_router.route_pull_request_event(
                action=action,
                pull_request=pull_request,
                repository=repository
            )
        
        elif event_type == "ping":
            logger.info("🏓 Ping event - webhook setup successful")
        
        else:
            logger.info(f"ℹ️  Received {event_type} event - no processing needed")
    
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}", exc_info=True)


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """GitHub webhook receiver endpoint.
    
    Security: Verifies HMAC signature before processing.
    Performance: Returns 200 immediately, processes in background.
    
    Returns:
        200: Webhook received and queued for processing
        401: Invalid or missing signature
        400: Malformed payload
    """
    # Get signature header
    signature = request.headers.get("X-Hub-Signature-256")
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    
    # Read raw body for signature verification
    try:
        body = await request.body()
    except Exception as e:
        logger.error(f"Failed to read request body: {e}")
        raise HTTPException(status_code=400, detail="Invalid request body")
    
    # Verify signature
    try:
        verify_github_signature(body, signature)
    except WebhookSecurityError as e:
        logger.error(f"Webhook security check failed: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Log webhook receipt
    logger.info(f"✅ Webhook verified: {event_type}")
    
    # Queue background processing
    background_tasks.add_task(process_webhook_background, event_type, payload)
    
    # Return 200 immediately
    return {
        "status": "received",
        "event": event_type,
        "message": "Webhook queued for processing"
    }
