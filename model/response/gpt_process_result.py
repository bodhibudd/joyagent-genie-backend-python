from typing import Optional

from pydantic import BaseModel, Field


class GptProcessResult(BaseModel):
    status: Optional[str] = None
    response: Optional[str] = ""
    response_all: Optional[str] = Field("", alias="responseAll", description="全量内容回复")
    finished: Optional[bool] = False
    use_times: Optional[int] = Field(0, alias="useTimes")
    user_tokens: Optional[int] = Field(0, alias="useTokens")
    result_map: Optional[dict] = Field(None, alias="resultMap", description="结构化输出结果")
    response_type: Optional[str] = Field("markdown", alias="responseType", description="大模型响应内容类型")
    trace_id: Optional[str] = Field(None, alias="traceId", description="会话ID")
    req_id: Optional[str] = Field(None, alias="reqId")
    encrypted: Optional[bool] = Field(False, alias="encrypted")
    query: Optional[str] = None
    messages: Optional[list] = None
    package_type: Optional[str] = Field("result", alias="packageType")
    error_msg: Optional[str] = Field(None, alias="errorMsg")

    class Config:
        populate_by_name = True
