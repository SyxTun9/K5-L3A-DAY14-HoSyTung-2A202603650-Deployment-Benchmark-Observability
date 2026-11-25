"""
Cost guard (tiêu chí 8) — lưu tổng chi phí theo ngày trên Redis.
"""
import time
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_cost_key() -> str:
    return f"cost:daily:{time.strftime('%Y-%m-%d')}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget -> raise HTTPException(status_code=402)."""
    if r is None:
        raise HTTPException(status_code=503, detail="Redis client not configured")

    raw = r.get(_daily_cost_key())
    spent = float(raw) if raw is not None else 0.0
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget exceeded (${spent:.6f} / ${settings.daily_budget_usd:.2f})",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is not None:
        key = _daily_cost_key()
        r.incrbyfloat(key, cost)
        r.expire(key, 172800)  # 48h
    return cost
