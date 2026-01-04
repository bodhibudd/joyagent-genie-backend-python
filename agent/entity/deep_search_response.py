from typing import List, Optional
from pydantic import Field, BaseModel


class SearchDoc(BaseModel):
    doc_type: Optional[str] = None
    content: Optional[str] = None
    title: Optional[str] = None
    link: Optional[str] = None


class SearchResult(BaseModel):
    query: Optional[List[str]] = None
    docs: Optional[List[List[SearchDoc]]] = None


class DeepSearchResponse(BaseModel):
    request_id: str = Field(None, alias="requestId")
    query: Optional[str] = None
    answer: Optional[str] = None
    search_result: Optional[SearchResult] = Field(None, alias="searchResult")
    is_final: Optional[bool] = Field(None, alias="isFinal")
    search_finish: Optional[bool] = Field(None, alias="searchFinish")
    message_type: Optional[str] = Field(None, alias="messageType")

    class Config:
        populate_by_name = True