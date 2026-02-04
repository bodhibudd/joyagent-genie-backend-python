import json

from agent.agent.agent_context import AgentContext
from agent.agent.react_agent import ReActAgent
from agent.agent.summary_agent import SummaryAgent
from handler.agent_handler import AgentHandler
from config.genie_config import GenieConfig
from agent.entity.enums import AgentType
from model.protocal import AgentRequest
from model.response.agent_response import build_stream_response


class ReactHandler(AgentHandler):
    def __init__(self, genie_config: GenieConfig):
        super(ReactHandler, self).__init__(genie_config)
        self.genie_config = genie_config

    async def handle(self, context: AgentContext, request: AgentRequest):
        executor = ReActAgent(context)
        summary = SummaryAgent(context)
        summary.system_prompt = summary.system_prompt.replace("{{query}}", request.query)
        await executor.run(request.query)
        summary_result = summary.summary_task_result(executor.memory.messages, request.query)

        # 组装结果
        task_result = {}
        task_result["taskSummary"]=summary_result.task_summary
        if summary_result.files is None or len(summary_result.files) == 0:
            if context.product_files is not None and len(context.product_files) != 0:
                task_result["fileList"] = [file for file in reversed(context.product_files) if not file.get("is_internal_file", None)]
        else:
            task_result["fileList"] = summary_result.files
        data = build_stream_response(context.request_id, context.agent_type, None, "result", task_result, None, True)

        await context.queue.put("[DONE]"+data)
        return data

    def support(self, agent_type):
        return AgentType.REACT.value == agent_type

