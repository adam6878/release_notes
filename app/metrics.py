from prometheus_client import Counter, Histogram

REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["method", "path"])
