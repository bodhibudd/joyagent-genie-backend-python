from typing import Optional

from pydantic import BaseModel, Field


class EventMessage(BaseModel):
    task_id: Optional[str] = Field(None, alias="taskId")
    task_order: Optional[int] = Field(None, alias="taskOrder")
    message_id: Optional[str] = Field(None, alias="messageId")
    message_type: Optional[str] = Field(None, alias="messageType")
    message_order: Optional[int] = Field(None, alias="messageOrder")
    result_map: Optional[dict] = Field(None, alias="resultMap")

    class Config:
        populate_by_name = True
