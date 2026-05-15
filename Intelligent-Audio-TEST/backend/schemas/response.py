from typing import Any, Generic, Optional, TypeVar

from pydantic import Field

from backend.schemas.base import APIModel
from backend.utils.error_codes import ErrorCode

T = TypeVar("T")


class ApiResponse(APIModel, Generic[T]):
    success: bool = Field(default=True)
    code: int = Field(default=int(ErrorCode.SUCCESS))
    message: str = Field(default="Success")
    data: Optional[T] = Field(default=None)
    detail: Optional[Any] = Field(default=None)

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "Success", code: int = int(ErrorCode.SUCCESS)) -> "ApiResponse[T]":
        success = int(code) == int(ErrorCode.SUCCESS) or int(code) == 200
        return cls(success=success, code=int(code), message=message, data=data)

    @classmethod
    def fail(
        cls,
        message: str = "Error",
        code: int = int(ErrorCode.OPERATION_FAILED),
        detail: Optional[Any] = None,
    ) -> "ApiResponse[Any]":
        success = int(code) == int(ErrorCode.SUCCESS) or int(code) == 200
        return cls(success=success, code=int(code), message=message, data=None, detail=detail)
