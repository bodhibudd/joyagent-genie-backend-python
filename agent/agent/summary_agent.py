import json
import re
import traceback

from loguru import logger

from agent.agent.agent_context import AgentContext
from agent.agent.base_agent import BaseAgent
from typing import Optional, List

from agent.agent.message import Message
from agent.entity.file import TaskSummaryResult, File
from agent.llm.llm import LLM
from config.genie_config import genie_config


class SummaryAgent(BaseAgent):
    log_flag = "summaryTaskResult"

    def __init__(
            self,
            context: Optional[AgentContext] = None,
    ):
        super().__init__(context=context)
        self.context = context
        self.request_id = context.request_id
        self.system_prompt = genie_config.summary_system_prompt
        self.llm = LLM(genie_config.planner_model_name if context.agent_type == 3 else genie_config.react_model_name,
                       llm_erp="")
        self.message_size_limit = genie_config.message_size_limit

    async def step(self):
        return ""

    def _create_file_info(self):
        files = self.context.product_files
        if files is None or len(files) == 0:
            logger.info(f"requestId: {self.context.request_id} no files found in context")
            return ""
        logger.info(f"requestId: {self.context.request_id} {SummaryAgent.log_flag} product files:{files}")
        results = []
        for file in files:
            file = File.model_validate_json(json.dumps(file, ensure_ascii=False))
            if file.is_internal_file:
                continue
            results.append(file.file_name+" : "+file.description)
        logger.info(f"requestId: {self.context.request_id} generated file info: {results}")
        return "\n".join(results)

    def _format_system_prompt(self, task_history, query):
        if self.system_prompt is None:
            logger.error(f"requestId: {self.context.request_id} {SummaryAgent.log_flag} systemPrompt is null")
            raise Exception("System prompt is not configured")

        return self.system_prompt.replace("{{taskHistory}}", task_history)\
            .replace("{{query}}", query)\
            .replace("{{fileNameDesc}}", self._create_file_info())

    def _parse_llm_response(self, response):
        if len(response) == 0:
            logger.error(f"requestId: {self.context.request_id} pattern matcher failed for response is null")
            return TaskSummaryResult(task_summary="")
        parts1 = re.split(r"\$\$\$", response)
        if len(parts1) < 2:
            return TaskSummaryResult(task_summary=parts1[0])
        summary = parts1[0]
        file_names = parts1[1]
        files = self.context.product_files
        if len(files) != 0:
            files = list(reversed(files))
        else:
            return TaskSummaryResult(task_summary=summary)
        product = list()
        items = file_names.split("、")
        for item in items:
            if len(item.lstrip().rstrip()) == 0:
                continue
            for file in files:
                file = File.model_validate_json(json.dumps(file, ensure_ascii=False))
                if file.file_name.strip() in item:
                    logger.info(f"requestId: {self.context.request_id} add file:{file}")
                    product.append(file.model_dump(by_alias=True))
                    break

        return TaskSummaryResult(task_summary=summary, files=product)

    def summary_task_result(
            self,
            messages: Optional[List[Message]] = None,
            query: Optional[str] = ""
    ):
        #参数校验
        if messages is None or len(messages) == 0 or len(query) == 0:
            logger.warning(f"requestId: {self.context.request_id} summaryTaskResult messages: {messages} or query:{query} is empty")
            return TaskSummaryResult(task_summary="")

        try:
            logger.info(f"requestId: {self.context.request_id} summaryTaskResult: messages:{messages}")
            format_messages = []
            for message in messages:
                content = message.content
                if content is not None and len(content) > self.message_size_limit:
                    logger.info(f"requestId: {self.context.request_id} message truncate, {message}")
                    content = content[:self.message_size_limit]
                format_messages.append(f"role:{message.role.value} content:{content}")
            formatted_prompt = self._format_system_prompt("\n".join(format_messages), query)
            user_message = Message.user_message(formatted_prompt, None)
            summary_response = self.llm.ask(self.context, [user_message], [], stream=False, temperature=0.01)
            logger.info(f"requestId: {self.context.request_id} summaryTaskResult: {summary_response}")

            return self._parse_llm_response(summary_response)
        except Exception as e:
            logger.error(f"requestId: {self.context.request_id} in summaryTaskResult failed,{str(e)}")
            logger.error(traceback.format_exc())
            return TaskSummaryResult(task_summary="任务执行失败，请联系管理员!")
