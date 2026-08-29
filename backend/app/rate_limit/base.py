from abc import ABC, abstractmethod


class LoginRateLimiter(ABC):
    @abstractmethod
    def is_blocked(self, key: str) -> bool:
        ...

    @abstractmethod
    def record_failure(self, key: str) -> None:
        ...

    @abstractmethod
    def reset(self, key: str) -> None:
        ...

    def ping(self) -> bool:
        return True
