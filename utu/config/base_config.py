from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..utils.security import redact_sensitive_data

ReprArgs: type = Iterable[tuple[str | None, Any]]


def secure_repr(obj: ReprArgs) -> ReprArgs:
    for k, v in obj:
        yield k, redact_sensitive_data(v, _parent_key=k)


class ConfigBaseModel(BaseModel):
    """Base model for config, with secure repr"""

    # Configuration files are part of the experiment contract.  Silently
    # discarding a misspelled or stale option makes the resolved YAML diverge
    # from the runtime behaviour, so all typed config models are strict by
    # default.  Fields intentionally designed as extension points (for
    # example ``ToolkitConfig.config``) remain ordinary dictionaries and may
    # contain arbitrary provider-specific keys.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

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
