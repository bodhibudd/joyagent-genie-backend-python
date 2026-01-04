from pydantic import BaseModel, Field
from typing import List, Optional


class Message(BaseModel):
    role: str = Field(alias="role", description="role")
    content: str = Field(alias="content", description="content")
    command_code: Optional[str] = Field(default=None, alias="commandCode", description="commandCode")
    upload_file: Optional[str] = Field(default=None, alias="uploadFile", description="uploadFile")
    files: Optional[str] = Field(default=None, alias="files", description="files")

    class Config:
        populate_by_name = True


class AgentRequest(BaseModel):
    request_id: str = Field(default="", alias="requestId", description="Request ID")
    erp: str = Field(default="", description="erp")
    query: str = Field(default="", description="query")
    agent_type: Optional[int] = Field(default=None,alias="agentType", description="agentType")
    base_prompt: str = Field(default="", alias="basePrompt", description="basePrompt")
    sop_prompt: str = Field(default="", alias="sopPrompt", description="sopPrompt")
    is_stream: bool = Field(default=False, alias="isStream", description="isStream")
    messages: Optional[List[Message]] = Field(default=None,description="messages")
    output_style: str = Field(default="html", alias="outputStyle", description="outputStyle")

    class Config:
        populate_by_name = True




class FileInformation(BaseModel):
    file_name: str = Field(alias="fileName", description="fileName")
    file_desc: str = Field(alias="fileDesc", description="fileDesc")
    oss_url: str = Field(alias="ossUrl", description="ossUrl")
    domain_url: str = Field(alias="domainUrl", description="domainUrl")
    file_size: str = Field(alias="fileSize", description="fileSize")
    file_type: str = Field(alias="fileType", description="fileType")
    origin_file_name: str = Field(alias="originFileName", description="originFileName")
    origin_file_url: str = Field(alias="originFileUrl", description="originFileUrl")
    origin_oss_url: str = Field(alias="originOssUrl", description="originOssUrl")
    origin_domain_url: str = Field(alias="originDomainUrl", description="originDomainUrl")

    class Config:
        populate_by_name = True


class GptQueryReq(BaseModel):
    query: str = Field(description="query")
    session_id: str = Field(alias="sessionId", description="sessionId")
    request_id: str = Field(alias="requestId", description="Request ID")
    deep_think: int = Field(None,alias="deepThink", description="deepThink")
    output_style: str = Field(None,alias="outputStyle", description="outputStyle")
    trace_id: str = Field(None,alias="traceId", description="traceId")
    user: str = Field(None,description="user")

    class Config:
        populate_by_name = True
