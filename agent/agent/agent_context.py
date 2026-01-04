from pydantic import BaseModel, Field
from typing import Optional, List

from agent.tool.base_tool import BaseTool
from agent.tool.mcp_tool import McpTool
from loguru import logger
from asyncio import Queue
from dataclasses import dataclass


class McpToolInfo(BaseModel):
    mcp_server_url: Optional[str] = None
    name: Optional[str] = None
    desc: Optional[str] = None
    parameters: Optional[str] = None


class ToolCollection:
    def __init__(
            self,
            agent_context: 'AgentContext' = None,
            tool_map: dict = None,
            mcp_tool_map: dict = None,
            current_task: Optional[str] = None,
            digital_employees: Optional[dict] = None
    ):
        self.agent_context = agent_context
        self.tool_map = {} if tool_map is None else tool_map
        self.mcp_tool_map = {} if mcp_tool_map is None else mcp_tool_map
        # 数字员工列表相关
        self.current_task = current_task
        self.digital_employees = digital_employees

    def add_tool(self, tool: BaseTool):
        self.tool_map[tool.name] = tool

    def get_tool(self, name) -> BaseTool:
        return self.tool_map[name]

    def add_mcp_tool(self, name, desc, params, mcp_server_url):
        self.mcp_tool_map[name] = McpToolInfo(name=name, desc=desc, parameters=params, mcp_server_url=mcp_server_url)

    def get_mcp_tool(self, name):
        return self.mcp_tool_map[name]

    async def execute(self, name, tool_input):
        if name in self.tool_map:
            tool = self.get_tool(name)
            return await tool.execute(tool_input)
        elif name in self.mcp_tool_map:
            tool_info = self.get_mcp_tool(name)
            mcp_tool = McpTool(self.agent_context)
            return await mcp_tool.call_tool(tool_info.mcp_server_url, name, tool_input)
        else:
            logger.error(f"Error: Unknown tool {name}")

        return None

    def update_digital_employee(
            self,
            digital_employee
    ):
        """设置数字员工"""
        if digital_employee is None:
            logger.error(f"requestId:{self.agent_context.request_id} setDigitalEmployee: {digital_employee}")

        self.digital_employees = digital_employee

    def get_digital_employee(self, tool_name):
        """获取数字员工名称"""
        if not tool_name or len(tool_name) == 0:
            return None
        if not self.digital_employees:
            return None

        return self.digital_employees.get(tool_name, None)


@dataclass
class AgentContext:
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    query: Optional[str] = None
    task: Optional[str] = None
    tool_collection: Optional['ToolCollection'] = None
    date_info: Optional[str] = None
    product_files: Optional[list] = None
    is_stream: Optional[bool] = None
    stream_message_type: Optional[str] = None
    sop_prompt: Optional[str] = None
    base_prompt: Optional[str] = None
    agent_type: Optional[int] = None
    task_product_files: Optional[list] = None
    template_type: Optional[str] = None
    queue: Optional[Queue] = None
