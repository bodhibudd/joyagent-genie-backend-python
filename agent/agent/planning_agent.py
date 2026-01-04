from loguru import logger

from agent.agent.agent_context import AgentContext
from agent.entity.enums import RoleType, ToolChoice, AgentState
from agent.agent.message import Message
from agent.agent.react_agent import BaseReActAgent
from typing import Optional

from agent.llm.llm import LLM
from agent.tool.common.planning_tool import PlanningTool, PlanningPrompt
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response
from util import file_util


class PlanningAgent(BaseReActAgent):
    def __init__(
            self,
            context: Optional[AgentContext] = None
    ):
        super().__init__(context=context)
        self.name = "planning"
        self.description = "An agent that creates and manages plans to solve tasks"
        self.max_steps = genie_config.planner_max_steps
        self.llm = LLM(genie_config.planner_model_name, "")
        self.context = context
        self.is_close_update = ("1" == genie_config.planning_close_update)
        self.planning_tool = PlanningTool()

        self.available_tools.add_tool(self.planning_tool)

        # 组装提示词,系统提示词中并不存在{{tools}}，用不到这块逻辑
        tool_prompt = list()
        for tool_name in context.tool_collection.tool_map:
            tool_prompt.append(f"工具名：{tool_name} 工具描述：{context.tool_collection.tool_map[tool_name].desc}")

        self.system_prompt = genie_config.planner_system_prompt_dict.get("default", PlanningPrompt.SYSTEM_PROMPT) \
            .replace("{{tools}}", "\n".join(tool_prompt)) \
            .replace("{{query}}", context.query) \
            .replace("{{date}}", context.date_info) \
            .replace("{{sopPrompt}}", context.sop_prompt)
        self.next_step_prompt = genie_config.planner_next_step_prompt_dict.get("default",
                                                                               PlanningPrompt.NEXT_STEP_PROMPT) \
            .replace("{{tools}}", "\n".join(tool_prompt)) \
            .replace("{{query}}", context.query) \
            .replace("{{date}}", context.date_info) \
            .replace("{{sopPrompt}}", context.sop_prompt)

        self.system_prompt_snapshot = self.system_prompt
        self.next_step_prompt_snapshot = self.next_step_prompt

    async def think(self):
        # 获取文件内容
        files_str = file_util.format_file_info(self.context.product_files, False)
        self.system_prompt = self.system_prompt_snapshot.replace("{{files}}", files_str)
        self.next_step_prompt = self.next_step_prompt_snapshot.replace("{{files}}", files_str)
        logger.info(f"{self.context.request_id} planer fileStr {files_str}")
        if self.is_close_update:
            if self.planning_tool.plan is not None:
                self.planning_tool.step_plan()
                return True

        try:
            if self.memory.get_last_message().role != RoleType.USER:
                self.memory.add_message(Message.user_message(self.next_step_prompt, None))

            self.context.stream_message_type = "plan_thought"
            plan_response = await self.llm.ask_tool(
                self.context,
                self.memory.messages,
                Message.system_message(self.system_prompt, None),
                self.available_tools,
                ToolChoice.AUTO.value,
                self.context.is_stream,
                300,
                None
            )
            self.tool_calls = plan_response.tool_calls

            if not self.context.is_stream and plan_response.content is not None and len(plan_response.content) != 0:
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "plan_thought",
                    plan_response.content,
                    None,
                    True
                )
                await self.context.queue.put(data)
            logger.info(f"{self.context.request_id} {self.name}'s thoughts: {plan_response.content}")
            logger.info(
                f"{self.context.request_id} {self.name} selected {0 if plan_response.tool_calls is None else len(plan_response.tool_calls)} tools to use")

            if plan_response.tool_calls is not None and len(
                    plan_response.tool_calls) != 0 and "struct_parse" != self.llm.function_call_type:
                assistant_msg = Message.from_tool_calls(plan_response.content, plan_response.tool_calls)
            else:
                assistant_msg = Message.assistant_message(plan_response.content, None)

            self.memory.add_message(assistant_msg)
        except Exception:
            logger.error(f"{self.context.request_id} think error")

        return True

    async def act(self):
        if self.is_close_update:
            if self.planning_tool.plan is not None:
                return await self._get_next_task()

        results = list()
        for tool_call in self.tool_calls:
            result = await self.execute_tool(tool_call)
            results.append(result)
            if "struct_parse" == self.llm.function_call_type:
                content = self.memory.get_last_message().content + "\n 工具执行结果为:\n" + result
                self.memory.get_last_message().content = content
            else:
                self.memory.add_message(Message.tool_messsage(result, tool_call.id, None))

        if self.planning_tool.plan is not None:
            if self.is_close_update:
                self.planning_tool.step_plan()
                return await self._get_next_task()

        return "\n\n".join(results)

    async def _get_next_task(self):
        all_complete = True
        for status in self.planning_tool.plan.step_status:
            if status != "completed":
                all_complete = False
                break
        if all_complete:
            self.state = AgentState.FINISHED
            data = build_stream_response(
                self.context.request_id,
                self.context.agent_type,
                None,
                "plan",
                self.planning_tool.plan.model_dump(),
                None,
                True
            )
            await self.context.queue.put(data)
            return "finish"
        if len(self.planning_tool.plan.get_current_step()) != 0:
            self.state = AgentState.FINISHED
            current_steps = self.planning_tool.plan.get_current_step().split("<sep>")
            data = build_stream_response(
                self.context.request_id,
                self.context.agent_type,
                None,
                "plan",
                self.planning_tool.plan.model_dump(),
                None,
                True
            )
            await self.context.queue.put(data)
            for step in current_steps:
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "task",
                    step,
                    None,
                    True
                )
                await self.context.queue.put(data)
            return self.planning_tool.plan.get_current_step()

        return ""

    async def run(self, query: str):
        if self.planning_tool.plan is None:
            query = genie_config.plan_pre_prompt + query

        return await super().run(query)
