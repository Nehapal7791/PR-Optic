"""Structured step logging for review pipeline.

Provides timestamped logging for each step in the review process.
"""

from datetime import datetime
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


class StepLogger:
    """Logger for pipeline steps with timestamps and context."""
    
    def __init__(self, pr_id: str, operation: str):
        """Initialize step logger.
        
        Args:
            pr_id: PR identifier (owner/repo/number)
            operation: Operation name (e.g., 'review', 'verify_fixes')
        """
        self.pr_id = pr_id
        self.operation = operation
        self.step_count = 0
        self.start_time = datetime.utcnow()
    
    def log_step(self, step_name: str, details: dict[str, Any] | None = None):
        """Log a pipeline step with timestamp.
        
        Args:
            step_name: Name of the step
            details: Optional additional details
        """
        self.step_count += 1
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        
        log_data = {
            "pr_id": self.pr_id,
            "operation": self.operation,
            "step": self.step_count,
            "step_name": step_name,
            "elapsed_seconds": round(elapsed, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if details:
            log_data.update(details)
        
        logger.info(
            f"[{self.pr_id}] STEP {self.step_count}: {step_name} (t+{elapsed:.2f}s)",
            extra=log_data
        )
    
    def log_route(self, route: str, reason: str):
        """Log routing decision.
        
        Args:
            route: Route taken (e.g., 'run_review', 'verify_fixes')
            reason: Reason for routing decision
        """
        logger.info(
            f"🔀 ROUTING: {route} | PR: {self.pr_id} | Reason: {reason}",
            extra={
                "pr_id": self.pr_id,
                "route": route,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_error(self, step_name: str, error: Exception):
        """Log step error.
        
        Args:
            step_name: Name of the step that failed
            error: Exception that occurred
        """
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        
        logger.error(
            f"[{self.pr_id}] STEP {self.step_count + 1} FAILED: {step_name} (t+{elapsed:.2f}s) - {error}",
            exc_info=True,
            extra={
                "pr_id": self.pr_id,
                "operation": self.operation,
                "step": self.step_count + 1,
                "step_name": step_name,
                "error": str(error),
                "error_type": type(error).__name__,
                "elapsed_seconds": round(elapsed, 2),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_completion(self, result: str):
        """Log operation completion.
        
        Args:
            result: Result summary
        """
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        
        logger.info(
            f"[{self.pr_id}] ✅ COMPLETE: {self.operation} - {result} (total: {elapsed:.2f}s)",
            extra={
                "pr_id": self.pr_id,
                "operation": self.operation,
                "total_steps": self.step_count,
                "result": result,
                "total_seconds": round(elapsed, 2),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


def log_routing_decision(pr_id: str, action: str, route: str, reason: str):
    """Log routing decision for webhook events.
    
    Args:
        pr_id: PR identifier
        action: GitHub action (opened, synchronize, etc.)
        route: Route taken (run_review, verify_fixes, skip)
        reason: Reason for decision
    """
    logger.info(
        f"🔀 ROUTING: {route} | PR: {pr_id} | Action: {action} | Reason: {reason}",
        extra={
            "pr_id": pr_id,
            "action": action,
            "route": route,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
