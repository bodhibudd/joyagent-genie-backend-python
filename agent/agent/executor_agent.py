import json
from typing import Optional, List

from loguru import logger
import json_repair
from agent.agent.agent_context import AgentContext
from agent.entity.enums import RoleType, ToolChoice, AgentState
from agent.agent.message import Message, ToolCall
from agent.agent.react_agent import BaseReActAgent
from agent.llm.llm import LLM
from agent.prompt.tool_call_prompt import ToolCallPrompt
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response, ToolResult
from util import file_util


class ExecutorAgent(BaseReActAgent):
    def __init__(
            self,
            context: Optional[AgentContext] = None,
            tool_calls: Optional[List[ToolCall]] = None
    ):
        super().__init__(context=context)
        self.name = "executor"
        self.description = "an agent that can execute tool calls."
        tool_prompt = list()
        for tool_name in context.tool_collection.tool_map:
            tool_prompt.append(f"工具名：{tool_name} 工具描述：{context.tool_collection.tool_map[tool_name].desc}")

        self.system_prompt = genie_config.executor_system_prompt_dict.get("default", ToolCallPrompt.SYSTEM_PROMPT) \
            .replace("{{tools}}", "\n".join(tool_prompt)) \
            .replace("{{query}}", context.query) \
            .replace("{{date}}", context.date_info) \
            .replace("{{sopPrompt}}", context.sop_prompt) \
            .replace("{{executorSopPrompt}}", genie_config.executor_sop_prompt_dict.get("default", ""))
        self.next_step_prompt = genie_config.executor_next_step_prompt_dict.get("default",
                                                                               ToolCallPrompt.NEXT_STEP_PROMPT) \
            .replace("{{tools}}", "\n".join(tool_prompt)) \
            .replace("{{query}}", context.query) \
            .replace("{{date}}", context.date_info) \
            .replace("{{sopPrompt}}", context.sop_prompt) \
            .replace("{{executorSopPrompt}}", genie_config.executor_sop_prompt_dict.get("default", ""))

        self.system_prompt_snapshot = self.system_prompt
        self.next_step_prompt_snapshot = self.next_step_prompt

        self.context = context
        self.tool_calls = tool_calls
        self.max_steps = genie_config.executor_max_steps
        self.llm = LLM(genie_config.executor_model_name, "")
        self.max_observe = int(genie_config.max_observe)
        self.available_tools = context.tool_collection
        # 生成数字人的提示词
        self.digital_employee_prompt = genie_config.digital_employee_prompt
        self.task_id = 0

    async def think(self):
        files_str = file_util.format_file_info(self.context.product_files, True)
        self.system_prompt = self.system_prompt_snapshot.replace("{{files}}", files_str)
        self.next_step_prompt = self.next_step_prompt_snapshot.replace("{{files}}", files_str)
        if self.memory.get_last_message().role != RoleType.USER:
            self.memory.add_message(Message.user_message(self.next_step_prompt, None))

        try:
            logger.info(f"{self.context.request_id} executor ask tool {self.available_tools}")
            response = await self.llm.ask_tool(
                self.context,
                self.memory.messages,
                Message.system_message(self.system_prompt, None),
                self.available_tools,
                ToolChoice.AUTO.value,
                False,
                300,
                None
            )

            # 记录响应信息
            if response.content is not None and len(response.content.strip()) != 0:
                if len(response.tool_calls) == 0:
                    task_summary = dict()
                    task_summary["taskSummary"] = response.content
                    task_summary["fileList"] = self.context.task_product_files
                    data = build_stream_response(
                        self.context.request_id,
                        self.context.agent_type,
                        None,
                        "task_summary",
                        task_summary,
                        None,
                        True
                    )
                    await self.context.queue.put(data)
                else:
                    data = build_stream_response(
                        self.context.request_id,
                        self.context.agent_type,
                        None,
                        "tool_thought",
                        response.content,
                        None,
                        True
                    )
                    await self.context.queue.put(data)
            self.tool_calls = response.tool_calls
            if response.tool_calls is not None and len(response.tool_calls) != 0 and "struct_parse" != self.llm.function_call_type:
                assistant_msg = Message.from_tool_calls(response.content, response.tool_calls)
            else:
                assistant_msg = Message.assistant_message(response.content, None)

            self.memory.add_message(assistant_msg)

        except Exception as e:
            logger.error("0ops! The"+self.name + "'s thinking process hit a snag: " + str(e))
            self.memory.add_message(Message.assistant_message("Error encountered while processing: " + str(e), None))
            self.state = AgentState.FINISHED
            return False
        return True

    async def act(self):
        if self.tool_calls is None or len(self.tool_calls) == 0:
            self.state = AgentState.FINISHED
            if "1" == genie_config.clear_tool_message:
                self.memory.clear_tool_context()
            if len(genie_config.task_complete_desc) != 0:
                return genie_config.task_complete_desc
            return self.memory.get_last_message().content

        tool_results = await self.execute_tools(self.tool_calls)
        results = list()

        for tool_call in self.tool_calls:
            result = tool_results[tool_call.id]
            if tool_call.function.name not in ["code_interpreter", "report_tool", "file_tool", "knowledge_tool",
                                               "deep_search", "data_analysis"]:
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "tool_result",
                    ToolResult(tool_name=tool_call.function.name, tool_params=json_repair.loads(tool_call.function.arguments), tool_result=result).dict(),
                    None,
                    is_final=True
                )
                await self.queue.put(data)

            if self.max_observe is not None:
                result = result[:self.max_observe]

            # 添加工具响应到记忆
            if "struct_parse" == self.llm.function_call_type:
                self.memory.get_last_message().content = self.memory.get_last_message().content + "\n 工具执行结果为:\n" + result
            else:
                self.memory.add_message(Message.tool_messsage(result, tool_call.id, None))
            results.append(result)

        return "\n\n".join(results)

    async def run(self, query: str):
        # 数字员工设置
        self.generate_digital_employee(query)
        query = genie_config.task_pre_prompt + query
        self.context.task = query
        return await super().run(query)