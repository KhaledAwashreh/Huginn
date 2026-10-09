class TriggerRateLimitError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("pipeline trigger rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds
