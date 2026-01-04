import enum


class AgentType(enum.Enum):
    """agent类型"""
    COMPREHENSIVE = 1
    WORKFLOW = 2
    PLAN_SOLVE = 3
    ROUTER = 4
    REACT = 5


class RoleType(enum.Enum):
    """角色类型"""
    USER = "user"
    SYSTEM = "system"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AgentState(enum.Enum):
    """代理状态枚举"""
    IDLE = 1
    RUNNING = 2
    FINISHED = 3
    ERROR = 4


class ToolChoice(enum.Enum):
    """工具选择类型枚举"""
    NONE = "none"
    AUTO = "auto"
    REQUIRED = "required"


class AutoBotsResultStatus(enum.Enum):
    LOADING = "loading"
    NO = "no"
    RUNNING = "running"
    ERROR = "error"
    FINISHED = "finished"


class ResponseTypeEnum(enum.Enum):
    MARKDOWN = "markdown"
    TEXT = "text"
    CARD = "card"
