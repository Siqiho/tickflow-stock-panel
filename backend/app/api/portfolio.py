"""Per-account portfolio ledger API (no order execution)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.portfolio import PortfolioError, PortfolioWorkspace

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class HoldingInput(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    avg_cost: float = Field(gt=0)
    note: str = Field(default="", max_length=240)


def _workspace(request: Request) -> PortfolioWorkspace:
    return PortfolioWorkspace(request.app.state.repo.store.data_dir)


def _translate(exc: PortfolioError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("")
def portfolio_snapshot(request: Request) -> dict:
    try:
        return _workspace(request).snapshot(request.app.state.repo)
    except PortfolioError as exc:
        raise _translate(exc) from exc


@router.post("/holdings")
def save_holding(payload: HoldingInput, request: Request) -> dict:
    try:
        holding = _workspace(request).upsert(payload.model_dump())
        return {"ok": True, "holding": holding}
    except PortfolioError as exc:
        raise _translate(exc) from exc


@router.delete("/holdings/{symbol}")
def delete_holding(symbol: str, request: Request) -> dict:
    try:
        _workspace(request).delete(symbol)
        return {"ok": True}
    except PortfolioError as exc:
        raise _translate(exc) from exc

