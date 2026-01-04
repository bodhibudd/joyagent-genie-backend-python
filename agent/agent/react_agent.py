import json
import re
import traceback

from loguru import logger
import json_repair
from agent.agent.base_agent import BaseAgent
from typing import Optional, List
from agent.agent.message import Message, ToolCall
from agent.agent.agent_context import AgentContext
from agent.entity.enums import AgentState, RoleType, ToolChoice
from agent.llm.llm import LLM
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response, ToolResult
from util import file_util


class BaseReActAgent(BaseAgent):
    """ReAct代理基类"""

    def __init__(
            self,
            *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

    async def think(self):
        """思考过程"""
        pass

    async def act(self):
        """执行行动"""
        pass

    async def step(self):
        """执行单个步骤"""
        should_act = await self.think()
        if not should_act:
            return "Thinking complete - no action needed"
        return await self.act()

    def generate_digital_employee(self, task):
        # 参数检查
        if task is None or len(task) == 0:
            return
        try:
            format_digital_prompt = self.format_digital_prompt(task)
            user_message = Message.user_message(format_digital_prompt, None)

            result = self.llm.ask(
                self.context,
                [user_message],
                [],
                False,
                0.01
            )
            logger.info(f"requestId: {self.context.request_id} task:{task} generateDigitalEmployee: {result}")
            digital_employ_res = self.parse_digital_employee(result)
            if digital_employ_res is not None:
                logger.info(f"requestId:{self.context.request_id} generateDigitalEmployee: {digital_employ_res}")
                self.context.tool_collection.update_digital_employee(digital_employ_res)
                self.context.tool_collection.current_task = task
                # 更新available_tools 添加数字员工, 这一行可以去掉
                self.available_tools = self.context.tool_collection
            else:
                logger.error(f"requestId: {self.context.request_id} generateDigitalEmployee failed")
        except Exception:
            logger.error(f"requestId: {self.context.request_id} in generateDigitalEmployee failed")
            logger.error(traceback.format_exc())

    def format_digital_prompt(self, task):
        """提取系统提示格式化逻辑"""
        digital_employee_prompt = self.digital_employee_prompt
        if digital_employee_prompt is None:
            logger.error("System prompt is not configured")
            raise Exception("System prompt is not configured")
        tool_prompt = list()
        for tool in self.context.tool_collection.tool_map.values():
            tool_prompt.append(f"工具名: {tool.name} 工具描述: {tool.desc}")

        return digital_employee_prompt \
            .replace("{{task}}", task) \
            .replace("{{ToolsDesc}}", "\n".join(tool_prompt)) \
            .replace("{{query}}", self.context.query)

    def parse_digital_employee(self, dig_res):
        """
        格式：
        ```json
        {
            "file_tool": "市场洞察专员"
        }
        ```
        """
        if dig_res is None or len(dig_res) == 0:
            return None

        pattern = re.compile(r"```\s*json([\d\D]+?)```")
        match = pattern.match(dig_res)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                logger.error(f"requestId: {self.context.request_id} in parseDigitalEmployee error")

        return None


class ReActAgent(BaseReActAgent):
    def __init__(
            self,
            context: AgentContext,
            tool_calls: Optional[List[ToolCall]] = None,
            max_observe: Optional[int] = None
    ):
        super().__init__(context=context)
        self.name = "react"
        self.description = "an agent that can execute tool calls."
        self.genie_config = genie_config
        self.context = context
        self.tool_calls = tool_calls
        self.max_observe = max_observe

        tool_prompts = []
        for tool in context.tool_collection.tool_map.values():
            tool_prompts.append(f"工具名: {tool.name} 工具描述: {tool.desc}")

        self.system_prompt = genie_config.react_system_prompt_dict["default"] \
            .replace("{{tools}}", "\n".join(tool_prompts)) \
            .replace("{{query}}", context.query) \
            .replace("{{date}}", context.date_info) \
            .replace("{{basePrompt}}", context.base_prompt)
        self.next_step_prompt = genie_config.react_next_step_prompt_dict["default"] \
            .replace("{{tools}}", "\n".join(tool_prompts)) \
            .replace("{{query}}", context.query) \
            .replace("{{date}}", context.date_info) \
            .replace("{{basePrompt}}", context.base_prompt)

        self.system_prompt_snapshot = self.system_prompt
        self.next_step_prompt_snapshot = self.next_step_prompt
        self.llm = LLM(self.genie_config.react_model_name, "")

        self.queue = context.queue
        self.max_steps = genie_config.react_max_steps
        self.available_tools = context.tool_collection

    async def think(self):
        # 获取文件内容
        file_str = file_util.format_file_info(self.context.product_files, True)
        self.system_prompt = self.system_prompt_snapshot.replace("{{files}}", file_str)
        self.next_step_prompt = self.next_step_prompt_snapshot.replace("{{files}}", file_str)

        if self.memory.get_last_message().role != RoleType.USER:
            user_msg = Message.user_message(self.next_step_prompt, None)
            self.memory.add_message(user_msg)

        try:
            self.context.stream_message_type = "tool_thought"
            response = await self.llm.ask_tool(
                self.context,
                self.memory.messages,
                Message.system_message(self.system_prompt, None),
                self.available_tools,
                ToolChoice.AUTO.value,
                self.context.is_stream,
                300,
                None
            )
            self.tool_calls = response.tool_calls
            # 记录响应信息
            if not self.context.is_stream and response.content is not None and len(response.content) != 0:
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "tool_thought",
                    response.content,
                    None,
                    is_final=True
                )
                await self.queue.put(data)
            # 创建并添加助手信息
            if response.tool_calls is not None \
                    and len(response.tool_calls) != 0 \
                    and "struct_parse" != self.llm.function_call_type:
                assistant_msg = Message.from_tool_calls(response.content, response.tool_calls)
            else:
                assistant_msg = Message.assistant_message(response.content, None)

            self.memory.add_message(assistant_msg)

        except Exception as e:
            logger.error(f"{self.context.request_id} react think error" + traceback.format_exc())
            self.memory.add_message(
                Message.assistant_message(content=f"Error encountered while processing: {str(e)}", base64_image=None))
            self.state = AgentState.FINISHED
            return False

        return True

    async def act(self):
        if self.tool_calls is None or len(self.tool_calls) == 0:
            self.state = AgentState.FINISHED
            return self.memory.get_last_message().content

        tool_results = await self.execute_tools(self.tool_calls)
        results = list()
        for tool_call in self.tool_calls:
            result = tool_results[tool_call.id]
            if tool_call.function.name not in ["code_interpreter", "report_tool", "file_tool", "knowledge_tool",
                                               "deep_search", "data_analysis"]:
                tool_result = ToolResult(tool_name=tool_call.function.name,
                                         tool_params=json_repair.loads(tool_call.function.arguments),
                                         tool_result=result).dict()
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "tool_result",
                    tool_result,
                    None,
                    is_final=True
                )
                await self.queue.put(data)
            if self.max_observe is not None:
                result = result[0:self.max_observe]

            # 添加工具响应到记忆
            if "struct_parse" == self.llm.function_call_type:
                self.memory.get_last_message().content = self.memory.get_last_message().content + "\n 工具执行结果为:\n" + result
            else:
                self.memory.add_message(Message.tool_messsage(result, tool_call.id, None))
            results.append(result)

        return "\n\n".join(results)
