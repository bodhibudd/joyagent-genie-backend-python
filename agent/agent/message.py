from pydantic import BaseModel

from agent.entity.enums import RoleType
from typing import Optional, List


class Function(BaseModel):
    name: Optional[str] = None
    arguments: Optional[str] = None


class ToolCall(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    function: Optional[Function] = None


class Message(BaseModel):
    role: Optional[RoleType] = None
    content: Optional[str] = None
    base64_image: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: List[ToolCall] = None

    @classmethod
    def user_message(cls, content: str, base64_image: str):
        """用户消息"""
        return Message(role=RoleType.USER, content=content, base64_image=base64_image)

    @classmethod
    def system_message(cls, content: str, base64_image: str):
        """系统消息"""
        return Message(role=RoleType.SYSTEM, content=content, base64_image=base64_image)

    @classmethod
    def assistant_message(cls, content: str, base64_image: str):
        """助手消息"""
        return Message(role=RoleType.ASSISTANT, content=content, base64_image=base64_image)

    @classmethod
    def tool_messsage(cls, content: str, tool_call_id: str, base64_image: str):
        """工具消息"""
        return Message(role=RoleType.TOOL, content=content, tool_call_id=tool_call_id, base64_image=base64_image)

    @classmethod
    def from_tool_calls(cls, content: str, tool_calls: List[ToolCall]):
        """从工具调用创建消息"""
        return Message(role=RoleType.ASSISTANT, content=content, tool_calls=tool_calls)


class Memory:
    def __init__(self):
        self.messages: List[Message] = list()

    def add_message(self, message: Message):
        """添加消息"""
        self.messages.append(message)

    def add_messages(self, messages: List[Message]):
        """批量添加消息"""
        self.messages.extend(messages)

    def get_last_message(self):
        """获取最后一条消息"""
        return self.messages[-1] if len(self.messages) != 0 else None

    def clear(self):
        """清空消息"""
        self.messages.clear()

    #作用是什么？
    def clear_tool_context(self):
        """清空工具执行历史"""
        remove_messages = []
        for message in self.messages:
            if message.role == RoleType.TOOL:
                remove_messages.append(message)
                continue
            if message.role == RoleType.ASSISTANT and message.tool_calls is not None and len(message.tool_calls)!=0:
                remove_messages.append(message)
                continue
            if message.content.startswith("根据当前状态和可用工具，确定下一步行动"):
                remove_messages.append(message)
        for message in remove_messages:
            self.messages.remove(message)

    def format_messsages(self):
        """格式化message"""
        return "\n".join([f"role:{message.role.name} content:{message.content}" for message in self.messages])

    def size(self):
        """获取消息数量"""
        return len(self.messages)

    def is_empty(self):
        """判断是否为空"""
        return len(self.messages) == 0

    def get(self, index):
        """获取指定消息"""
        return self.messages[index] if self.size() > index else None
