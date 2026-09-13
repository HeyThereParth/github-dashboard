"""Version 1 API routers."""

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    github,
    issues,
    me,
    people,
    pull_requests,
    repositories,
    sync,
    users,
    webhooks,
    work,
    workspaces,
)

v1_router = APIRouter(prefix="/v1")

for sub_router in (
    me.router,
    users.router,
    workspaces.router,
    github.router,
    repositories.router,
    issues.router,
    pull_requests.router,
    people.router,
    work.router,
    analytics.router,
    webhooks.router,
    sync.router,
):
    v1_router.include_router(sub_router)
