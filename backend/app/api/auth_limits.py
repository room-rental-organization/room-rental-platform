from collections import OrderedDict, deque
import hashlib
from threading import Lock
from time import monotonic
from fastapi import HTTPException, Request
from app.core.config import get_settings


class AuthRequestLimiter:
    """Bounded per-process protection; email issuance also has DB-backed quotas."""
    def __init__(self) -> None:
        self.lock = Lock()
        self.buckets: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, request: Request, action: str, identity: str = '') -> None:
        if not get_settings().auth_rate_limit_enabled:
            return
        peer = request.client.host if request.client else 'unknown'
        now = monotonic()
        with self.lock:
            for scope, value, limit in [('peer', peer, 60), ('identity', identity.casefold(), 10)]:
                if not value:
                    continue
                key = hashlib.sha256(f'{action}:{scope}:{value}'.encode()).hexdigest()
                bucket = self.buckets.setdefault(key, deque())
                while bucket and bucket[0] <= now - 60:
                    bucket.popleft()
                if len(bucket) >= limit:
                    raise HTTPException(429, 'Too many attempts. Please wait a minute and try again.',
                                        headers={'Retry-After': '60'})
                bucket.append(now)
                self.buckets.move_to_end(key)
            while len(self.buckets) > 4096:
                self.buckets.popitem(last=False)


auth_limiter = AuthRequestLimiter()
