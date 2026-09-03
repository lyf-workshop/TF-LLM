from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from ..utils.security import is_sensitive_key, redact_sensitive_data

ReprArgs: type = Iterable[tuple[str | None, Any]]


def if_need_secure(key: str) -> bool:
    return is_sensitive_key(key)


def secure_repr(obj: ReprArgs) -> ReprArgs:
    for k, v in obj:
        yield k, redact_sensitive_data(v, _parent_key=k)


class ConfigBaseModel(BaseModel):
    """Base model for config, with secure repr"""

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({', '.join(f'{k}={v!r}' for k, v in secure_repr(self.__repr_args__()))})"

    def model_dump(
        self,
        *,
        exclude_none: bool = True,  # avoid passing temperature=None to avoid SGLang error
        **kwargs,
    ) -> dict[str, Any]:
        return super().model_dump(exclude_none=exclude_none, **kwargs)
