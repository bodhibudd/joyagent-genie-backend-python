import asyncio
import json_repair
import traceback
from typing import Optional, List
from agent.agent.agent_context import ToolCollection
from agent.agent.message import Memory, ToolCall
from agent.agent.agent_context import AgentContext
from agent.entity.enums import AgentState
from agent.entity.enums import RoleType
from agent.agent.message import Message
from loguru import logger
from concurrent.futures import ThreadPoolExecutor


class BaseAgent:

    def __init__(
            self,
            name: Optional[str] = None,
            description: Optional[str] = None,
            system_prompt: Optional[str] = None,
            next_step_prompt: Optional[str] = None,
            available_tools: Optional[ToolCollection] = None,
            memory: Optional[Memory] = None,
            llm=None,
            context: Optional[AgentContext] = None,
            state: Optional[AgentState] = None,
            max_steps: int = 10,
            current_step: int = 0,
            duplicate_threshold=2,
            queue: Optional[asyncio.Queue] = None,
            digital_employee_prompt: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.next_step_prompt = next_step_prompt
        self.available_tools = ToolCollection() if available_tools is None else available_tools
        self.memory = Memory() if memory is None else memory
        self.llm = llm
        self.context = context
        self.state = state
        self.max_steps = max_steps
        self.current_step = current_step
        self.current_step = current_step
        self.duplicate_threshold = duplicate_threshold
        self.queue = queue
        self.digital_employee_prompt = digital_employee_prompt

    async def step(self):
        pass

    async def run(self, query: str):
        """运行代理主循环"""
        self.state = AgentState.IDLE
        if len(query) != 0:
            # 修改记忆
            self.update_memory(RoleType.USER, query, None)
        results = list()
        try:
            while self.current_step < self.max_steps and self.state != AgentState.FINISHED:
                self.current_step += 1
                logger.info(
                    f"{self.context.request_id} {self.name} Executing step {self.current_step}/{self.max_steps}")
                step_result = await self.step()
                results.append(step_result)
            if self.current_step >= self.max_steps:
                self.current_step = 0
                self.state = AgentState.IDLE
                results.append(f"Terminated: Reached max steps ({self.max_steps}")
        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"{self.context.request_id} Terminated: {str(e)}")
            # raise Exception(traceback.format_exc()) todo,这里抛出异常会导致前端一直卡住，java版本这里是否需要注释掉
        return "No steps executed" if len(results) == 0 else results[-1]

    def update_memory(self, role: RoleType, content: str, base64_image, *args):
        if role.value == RoleType.USER.value:
            message = Message.user_message(content, base64_image)
        elif role.value == RoleType.ASSISTANT.value:
            message = Message.assistant_message(content, base64_image)
        elif role.value == RoleType.SYSTEM.value:
            message = Message.system_message(content, base64_image)
        elif role.value == RoleType.TOOL.value:
            message = Message.tool_messsage(content, args[0], base64_image)
        else:
            raise Exception(f"Unsupported role type: {role}")

        self.memory.add_message(message)

    async def execute_tool(self, command: ToolCall):
        error = ""
        try:
            if command is None or command.function is None or command.function.name is None:
                return "Error: Invalid function call format"
            name = command.function.name
            arguments = json_repair.loads(command.function.arguments)
            result = await self.available_tools.execute(name, arguments)
            if result is not None:
                return result
        except Exception as e:
            logger.error(f"{self.context.request_id} execute tool {name} failed")
            logger.error(traceback.format_exc())
            error = "reason:" + str(e)

        return "Tool:" + name + "Error." + error

    async def execute_tools(self, tool_calls: List[ToolCall]):
        """
        并发执行多个工具调用命令
        :tool_calls: 工具调用命令列表
        return: 返回工具执行结果映射，key为工具ID，value为执行结果
        """
        tasks = [asyncio.create_task(self.execute_tool(command)) for command in tool_calls]
        results = await asyncio.gather(*(task for task in tasks))
        result_dict = {}
        for result, tool_call in zip(results, tool_calls):
            result_dict[tool_call.id] = result

        return result_dict
