import asyncio
import json
import traceback

from agent.tool.common.code_interpreter_tool import CodeInterpreterTool
from agent.tool.common.deep_search_tool import DeepSearchTool
from agent.tool.common.file_tool import FileTool
from agent.tool.common.multi_modal_agent_tool import MultiModalAgent
from agent.tool.common.report_tool import ReportTool
from agent.tool.mcp_tool import McpTool
from model.protocal import AgentRequest
from agent.agent.agent_context import AgentContext, ToolCollection
from util import date_util
from handler.react_handler import ReactHandler
from handler.plan_solve_handler import PlanSolveHandler
from config.genie_config import genie_config
from loguru import logger
from langfuse import Langfuse
from langfuse.openai import OpenAI
langfuse = Langfuse(
    secret_key="sk-xxx",
    public_key="pk-xxx",
    host="https://cloud.langfuse.com"
)

def build_tool_collection(agent_context: AgentContext, agent_request: AgentRequest):
    tool_collection = ToolCollection(agent_context)
    if "dataAgent" == agent_request.output_style:
        pass # todo 智能问数暂未开发
    else:
        file_tool = FileTool(
            context=agent_context,
            queue = agent_context.queue
        )
        tool_collection.add_tool(file_tool)
        #default tool
        agent_tools = genie_config.multi_agent_tool_list_dict.get("default", ["search","code","report", "multimodalagent"])
        if len(agent_tools) != 0:
            if "code" in agent_tools:
                code_tool = CodeInterpreterTool(
                    context=agent_context,
                    queue=agent_context.queue
                )
                tool_collection.add_tool(code_tool)
            if "report" in agent_tools:
                html_tool = ReportTool(
                    context=agent_context,
                    queue=agent_context.queue
                )
                tool_collection.add_tool(html_tool)
            if "search" in agent_tools:
                deep_search_tool = DeepSearchTool(
                    context=agent_context,
                    queue=agent_context.queue
                )
                tool_collection.add_tool(deep_search_tool)
            if "multimodalagent" in agent_tools:
                multi_modal_agent_tool = MultiModalAgent(
                    context=agent_context,
                    queue=agent_context.queue
                )
                tool_collection.add_tool(multi_modal_agent_tool)

        try:
            mcp_tool = McpTool(
                agent_context=agent_context
            )
            for mcp_server in genie_config.mcp_server_url_arr:
                list_tool_result = mcp_tool.list_tool(mcp_server)
                if len(list_tool_result) == 0:
                    logger.error(f"{agent_context.request_id} mcp server {mcp_server} invalid")
                    continue
                resp = json.loads(list_tool_result)
                if int(resp["code"]) != 200:
                    logger.error(f"{agent_context.request_id} mcp serve {mcp_server} code: {resp['code']}, message: {resp['message']}")
                    continue
                data = resp["data"]
                if len(data) == 0:
                    logger.error(f"{agent_context.request_id} mcp serve {mcp_server} code: {resp['code']}, message: {resp['message']}")
                    continue
                for tool in data:
                    method = tool["name"]
                    description = tool["description"]
                    input_schema = json.dumps(tool["inputSchema"], ensure_ascii=False)
                    tool_collection.add_mcp_tool(method, description, input_schema, mcp_server)

        except Exception:
            logger.error(f"{agent_context.request_id} add mcp tool failed")

        return tool_collection


class AutoAgent(object):
    def __init__(self, queue):
        self.queue = queue or asyncio.Queue()
        self.handlers = [ReactHandler(genie_config), PlanSolveHandler(genie_config)]

    def _get_handler(self, agent_type):
        for handler in self.handlers:
            if handler.support(agent_type):
                return handler

    async def run(self, request: AgentRequest):
        try:
            agent_context = AgentContext()
            agent_context.request_id = request.request_id
            agent_context.session_id = request.request_id
            agent_context.query = request.query
            agent_context.task = ""
            agent_context.date_info = date_util.time_info()
            agent_context.product_files = list()
            agent_context.task_product_files = list()
            agent_context.sop_prompt = request.sop_prompt
            agent_context.base_prompt = request.base_prompt
            agent_context.agent_type = request.agent_type
            agent_context.is_stream = request.is_stream if request.is_stream is not None else False
            agent_context.template_type = "fix" if "dataAgent" == request.output_style else "empty"
            agent_context.queue = self.queue

            agent_context.tool_collection = build_tool_collection(agent_context, request)
            handler = self._get_handler(request.agent_type)
            with langfuse.start_as_current_observation(as_type="span", name=handler.__class__.__name__) as span:
                result = await handler.handle(agent_context, request)
                span.update_trace(
                    input= request.query,
                    output=result
                )
        except Exception as e:
            logger.error(f"{request.request_id} auto agent error")
            logger.error(traceback.format_exc())



