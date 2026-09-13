"""GitHub integration API schemas."""

from pydantic import BaseModel, Field


class GitHubConnectRequest(BaseModel):
    """Payload for linking a GitHub App installation to a workspace."""

    installation_id: int = Field(gt=0, description="GitHub App installation ID")


class GitHubInstallUrlResponse(BaseModel):
    """Response containing the GitHub App installation URL."""

    install_url: str


class GitHubRepositoryResponse(BaseModel):
    """Repository accessible via the connected GitHub App installation."""

    github_id: int
    node_id: str
    name: str
    full_name: str
    private: bool
    html_url: str
    default_branch: str
    description: str | None = None
