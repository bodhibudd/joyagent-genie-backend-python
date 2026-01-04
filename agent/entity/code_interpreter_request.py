from typing import List, Optional, Dict, Any
from pydantic import Field, BaseModel


class FileInfo(BaseModel):
    file_name: str = Field(..., alias="fileName")
    origin_file_name: str = Field(..., alias="originFileName")
    origin_oss_url: str = Field(..., alias="originOssUrl")

    class Config:
        populate_by_name = True


class CodeInterpreterRequest(BaseModel):
    request_id: str = Field(None, alias="requestId")
    query: Optional[str] = None
    task: Optional[str] = None
    file_names: Optional[List[str]] = Field(None, alias="fileNames")
    origin_file_names: Optional[List[FileInfo]] = Field(None, alias="originFileNames")
    file_name: Optional[str] = Field(None, alias="fileName")
    file_description: Optional[str] = Field(None, alias="fileDescription")
    file_type: Optional[str] = Field(None, alias="fileType")
    stream: Optional[bool] = None
    content_stream: Optional[bool] = Field(None, alias="contentStream")
    stream_mode: Optional[Dict[str, Any]] = Field(None, alias="streamMode")
    template_type: Optional[str] = Field(None, alias="templateType")

    class Config:
        populate_by_name = True
