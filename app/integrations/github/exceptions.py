"""GitHub integration exceptions."""


class GitHubIntegrationError(Exception):
    """Base exception for all GitHub integration errors."""


class GitHubAppConfigError(GitHubIntegrationError):
    """Raised when GitHub App credentials (App ID or Private Key) are missing or invalid."""


class GitHubAuthError(GitHubIntegrationError):
    """Raised when authenticating as an App or requesting an installation token fails."""


class GitHubRateLimitError(GitHubIntegrationError):
    """Raised when GitHub API rate limits are exceeded."""

    def __init__(self, message: str, reset_at: int | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class GitHubNotFoundError(GitHubIntegrationError):
    """Raised when a requested GitHub resource is not found (HTTP 404)."""


class GitHubAPIError(GitHubIntegrationError):
    """Raised when GitHub API returns an unexpected non-2xx status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code
