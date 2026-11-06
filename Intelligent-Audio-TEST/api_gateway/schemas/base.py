from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    """所有 API Schema 的基类。

    字段以 snake_case 定义，序列化输出也为 snake_case（不通过 alias 转换）。
    请求体仍可同时接受 snake_case 和 camelCase（alias_generator + populate_by_name）。
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        populate_by_alias=True,
        serialize_by_alias=False,     # 序列化输出原始字段名（snake_case）
        extra="ignore",
    )
