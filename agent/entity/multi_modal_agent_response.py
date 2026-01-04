from typing import List, Optional, Any
from pydantic import BaseModel, Field


class Delta(BaseModel):
    content: Optional[str] = None
    function_call: Optional[Any] = Field(None, alias="functionCall")
    refusal: Optional[str] = None
    role: Optional[str] = None
    tool_calls: Optional[Any] = Field(None, alias="toolCalls")

    class Config:
        populate_by_name = True


class Choice(BaseModel):
    delta: Optional[Delta] = None
    finish_reason: Optional[str] = Field(None, alias="finishReason")
    index: Optional[int] = None
    logprobs: Optional[Any] = None

    class Config:
        populate_by_name = True


class Usage(BaseModel):
    prompt_tokens: Optional[int] = Field(None, alias="promptTokens")
    completion_tokens: Optional[int] = Field(None, alias="completionTokens")
    total_tokens: Optional[int] = Field(None, alias="totalTokens")

    class Config:
        populate_by_name = True


class MultiModalAgentResponse(BaseModel):
    id: Optional[str] = None
    choices: Optional[List[Choice]] = None
    created: Optional[int] = None
    model: Optional[str] = None
    object: Optional[str] = None
    service_tier: Optional[str] = Field(None, alias="serviceTier")
    system_fingerprint: Optional[str] = Field(None, alias="systemFingerprint")
    usage: Optional[Usage] = None

    data: Optional[str] = None
    is_final: Optional[bool] = Field(None, alias="isFinal")

    class Config:
        populate_by_name = True