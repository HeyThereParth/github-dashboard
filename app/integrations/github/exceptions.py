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
