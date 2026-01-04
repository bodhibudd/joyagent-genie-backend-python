from pydantic import BaseModel

from typing import Optional, Dict, Any
from pydantic import Field


class DeepSearchRequest(BaseModel):
    request_id: str = Field(..., alias="request_id")
    query: Optional[str] = None
    erp: Optional[str] = None
    agent_id: Optional[str] = Field(None, alias="agent_id")
    optional_configs: Optional[Dict[str, Any]] = Field(None, alias="optional_configs")
    src_configs: Optional[Dict[str, Any]] = Field(None, alias="src_configs")
    scene_type: Optional[str] = Field(None, alias="scene_type")
    stream: Optional[bool] = None
    content_stream: Optional[bool] = Field(None, alias="content_stream")
