from typing import Optional
from pydantic import BaseModel, Field


class AutoBotsResult(BaseModel):
    status: Optional[str] = None
    response: Optional[str] = None  # 增量内容回复
    response_all: Optional[str] = Field(None, alias="responseAll")  # 全量内容回复
    finished: Optional[str] = None  # 是否结束
    use_times: Optional[int] = Field(0, alias="useTimes")
    use_tokens: Optional[int] = Field(0, alias="useTokens")
    result_map: Optional[dict] = Field(None, alias="resultMap")
    response_type: Optional[str] = Field("markdown", alias="responseType")
    trace_id: Optional[str] = Field(None, alias="traceId")
    req_id: Optional[str] = Field(None, alias="reqId")

    class Config:
        populate_by_name = True
