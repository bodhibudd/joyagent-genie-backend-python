from typing import Optional, List
from dataclasses import dataclass

from pydantic import BaseModel, Field


class File(BaseModel):
    oss_url: Optional[str] = Field(None, alias="ossUrl")
    domain_url: Optional[str] = Field(None, alias="domainUrl")
    file_name: Optional[str] = Field(None, alias="fileName")
    file_size: Optional[int] = Field(0, alias="fileSize")
    description: Optional[str] = None
    origin_file_name: Optional[str] = Field(None, alias="originFileName")
    origin_oss_url: Optional[str] = Field(None, alias="originOssUrl")
    origin_domain_url: Optional[str] = Field(None, alias="originDomainUrl")
    is_internal_file: Optional[bool] = Field(False, alias="isInternalFile")

    class Config:
        populate_by_name = True



@dataclass
class TaskSummaryResult:
    task_summary: Optional[str] = None
    files: Optional[List[File]] = None


class FileRequest(BaseModel):
    request_id: Optional[str] = Field(None, alias="requestId", description="Request ID")
    file_name: Optional[str] = Field(None, alias="fileName", description="fileName")
    description: Optional[str] = None
    content: Optional[str] = None

    class Config:
        populate_by_name = True
