"""
Rate limiting (tiêu chí 7) — sliding window lưu trên Redis.
"""
import time
import uuid
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Kiểm tra rate limit theo API key bằng Redis sorted set."""
    if r is None:
        raise HTTPException(status_code=503, detail="Redis client not configured")

    now = time.time()
    redis_key = f"ratelimit:{key}"
    window_start = now - WINDOW_SECONDS

    pipe = r.pipeline()
    pipe.zremrangebyscore(redis_key, 0, window_start)
    pipe.zcard(redis_key)
    _, count = pipe.execute()

    if count >= settings.rate_limit_per_minute:
        oldest = r.zrange(redis_key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest[0][1])) + 1)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    member = f"{now}:{uuid.uuid4().hex}"
    pipe = r.pipeline()
    pipe.zadd(redis_key, {member: now})
    pipe.expire(redis_key, WINDOW_SECONDS + 1)
    pipe.execute()
