"""Local-only news/policy reads and explicit refresh writes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.services import news as news_service

router = APIRouter(prefix="/api/news", tags=["news"])


def _data_dir(request: Request) -> Path:
    return Path(request.app.state.repo.store.data_dir)


class MarketRefreshBody(BaseModel):
    source: str = "all"


class PolicyRefreshBody(BaseModel):
    department: str = ""


class KeyDepartmentsBody(BaseModel):
    departments: list[str] = Field(default_factory=list)


@router.get("/market")
def get_market(request: Request) -> dict:
    return news_service.read_market(_data_dir(request))


@router.post("/market/refresh")
def post_market_refresh(request: Request, body: MarketRefreshBody) -> dict:
    return news_service.refresh_market(_data_dir(request), body.source)


@router.get("/policy")
def get_policy(
    request: Request,
    department: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 100,
) -> dict:
    return news_service.query_policy(
        _data_dir(request),
        department=department,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.post("/policy/refresh")
def post_policy_refresh(request: Request, body: PolicyRefreshBody) -> dict:
    return news_service.refresh_policy(_data_dir(request), department=body.department)


@router.get("/policy/departments")
def get_departments(request: Request) -> dict:
    return news_service.read_departments(_data_dir(request))


@router.post("/policy/departments/refresh")
def post_departments_refresh(request: Request) -> dict:
    return news_service.refresh_departments(_data_dir(request))


@router.get("/policy/key-departments")
def get_key_departments(request: Request) -> dict:
    return news_service.read_key_departments(_data_dir(request))


@router.post("/policy/key-departments")
def post_key_departments(request: Request, body: KeyDepartmentsBody) -> dict:
    return news_service.save_key_departments(body.departments, _data_dir(request))
