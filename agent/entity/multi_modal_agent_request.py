from typing import Optional

from pydantic import BaseModel, Field


class MultiModalAgentRequest(BaseModel):
    request_id: Optional[str] = Field(None, alias="requestId")
    question: Optional[str] = None
    query: Optional[str] = None
    stream: Optional[bool] = None
    content_stream: Optional[bool] = Field(None, alias="contentStream")
    stream_mode: Optional[dict] = Field(None, alias="streamMode")

    class Config:
        populate_by_name = True