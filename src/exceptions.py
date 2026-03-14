class PROpticError(Exception):
    """Base exception for PR-Optic application."""
    pass


class GitHubServiceError(PROpticError):
    """Raised when GitHub API operations fail."""
    
    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class ClaudeServiceError(PROpticError):
    """Raised when Claude API operations fail."""
    pass


class ReviewStateError(PROpticError):
    """Raised when review state operations fail."""
    pass
