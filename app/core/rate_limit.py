from slowapi import Limiter
from fastapi import Request

def get_forwarded_address(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

# Global limiter instance keyed by client remote IP address (or X-Forwarded-For header)
limiter = Limiter(key_func=get_forwarded_address)
