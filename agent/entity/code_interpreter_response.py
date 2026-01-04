from typing import List, Optional
from pydantic import Field, BaseModel


class FileInfo(BaseModel):
    file_name: str = Field(None, alias="fileName")
    oss_url: str = Field(None, alias="ossUrl")
    domain_url: str = Field(None, alias="domainUrl")
    file_size: Optional[int] = Field(None, alias="fileSize")

    class Config:
        populate_by_name = True


class CodeInterpreterResponse(BaseModel):
    requests_id: str = Field(None, alias="requestId")
    result_type: str = Field(None, alias="resultType")
    content: Optional[str] = None
    code: Optional[str] = None
    code_output: Optional[str] = Field(None, alias="codeOutput")
    file_info: Optional[List[FileInfo]] = Field(None, alias="fileInfo")
    explain: Optional[str] = None
    step: Optional[int] = None
    data: Optional[str] = None
    is_final: Optional[bool] = Field(None, alias="isFinal")

    class Config:
        populate_by_name = True