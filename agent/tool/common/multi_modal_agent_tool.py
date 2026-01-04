import asyncio
import traceback
import uuid
from typing import Optional
import requests
from loguru import logger

from agent.agent.agent_context import AgentContext
from agent.entity.file import FileRequest
from agent.entity.multi_modal_agent_request import MultiModalAgentRequest
from agent.entity.multi_modal_agent_response import MultiModalAgentResponse
from agent.tool.base_tool import BaseTool
from agent.tool.common.file_tool import FileTool
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response
from util import string_util


class MultiModalAgent(BaseTool):

    def __init__(
            self,
            context: Optional[AgentContext] = None,
            queue: Optional[asyncio.Queue] = None
    ):
        self.context = context
        self.queue = queue

    @property
    def name(self):
        return "multimodalagent_tool"

    @property
    def desc(self):
        desc = "本工具用于查询与用户相关的知识，作为在线知识的补充。支持文本和图像等多模态数据检索，能够高效访问和获取用户专属的知识信息。"
        return genie_config.multi_modal_agent_desc if len(genie_config.multi_modal_agent_desc) != 0 else desc

    @property
    def to_params(self):
        if genie_config.multi_modal_agent_params:
            return genie_config.multi_modal_agent_params

        parameters = dict()
        parameters["type"] = "object"
        parameters["properties"] = {
            "question": {"type": "string", "description": "查询所需要的question，需要在知识库中进行检索的检索短语或句子。"}}
        parameters["required"] = ["question"]

        return parameters

    async def execute(self, obj):
        try:
            question = obj.get("question", None)
            if question is None or len(question) == 0:
                logger.error(f"{self.context.request_id} question 为空无法调用知识库查询。")
                return None
            stream_mode = dict()
            stream_mode["mode"] = "token"
            stream_mode["token"] = 10
            multi_modal_req = MultiModalAgentRequest(
                request_id=self.context.session_id, # genie-tool端并没有该参数,
                question=question,# genie-tool端只有该参数,
                query=self.context.query,
                stream=True,
                content_stream=self.context.is_stream,
                stream_mode=stream_mode
            )
            multi_modal_res = await self.call_knowledge_agent_stream(multi_modal_req)
            return multi_modal_res
        except Exception:
            logger.error(f"{self.context.request_id} knowledge_tool error")
            logger.error(traceback.format_exc())

        return None

    async def call_knowledge_agent_stream(
            self,
            multi_modal_req: MultiModalAgentRequest
    ):
        url = genie_config.multi_modal_agent_url + "/v1/tool/mragQuery"
        intervals = genie_config.message_interval.get("knowledge", "1,4").split(",")
        first_interval = int(intervals[0])
        send_interval = int(intervals[1])
        index = 1
        message_id = str(uuid.uuid4())
        digital_employee = self.context.tool_collection.get_digital_employee(self.name)
        str_incr_list = list()
        str_all_list = list()
        try:
            with requests.post(url, json=multi_modal_req.model_dump(by_alias=True), stream=True,
                               timeout=(60, 600)) as response:
                if not response.ok:
                    logger.error(f"{multi_modal_req.request_id} multi_modal_agent_tool request error")
                    return
                for line in response.iter_lines():
                    if line is None or len(line) == 0:
                        continue
                    line = line.decode("utf8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if "[DONE]" == data:
                            break
                        logger.info(f"{self.context.request_id} knowledge_tool recv data: {data}")
                        if data.startswith("heartbeat"):
                            continue

                        # 解析为openai格式
                        multi_res = MultiModalAgentResponse.model_validate_json(data)
                        file_tool = FileTool()
                        file_tool.context = self.context
                        if multi_res.choices is not None and len(multi_res.choices) != 0:
                            choice = multi_res.choices[0]
                            if choice.delta is not None and choice.delta.content is not None:
                                content = choice.delta.content

                                # 特殊处理图片内容
                                if "![图片]" in content:
                                    logger.info(f"{self.context.request_id} knowledge_tool received image content: {content}")

                                str_incr_list.append(content)
                                str_all_list.append(content)

                                if index == first_interval or index % send_interval == 0:
                                    multi_res.data = "".join(str_incr_list)
                                    multi_res.is_final = False
                                    str_incr_list.clear()
                                if "stop" == choice.finish_reason:
                                    # 最终响应时使用累加的完整结果,并发送
                                    multi_res.data = "".join(str_all_list)
                                    multi_res.is_final = True
                                    logger.info(f"{self.context.request_id}### ==== all knowledge_tool recv data: {''.join(str_all_list)} ====")
                                    data = build_stream_response(
                                        self.context.request_id,
                                        self.context.agent_type,
                                        message_id,
                                        "markdown",
                                        multi_res.model_dump(by_alias=True),
                                        digital_employee,
                                        True
                                    )
                                    await self.queue.put(data)

                                    # 上传多模态检索结果文件
                                    file_name = string_util.remove_special_chars(self.context.query + "的多模态检索结果.md")
                                    file_desc = "".join(str_all_list)[:genie_config.deep_search_tool_file_desc_truncate_len]+"..."
                                    file_req = FileRequest(
                                        request_id=self.context.request_id,
                                        file_name=file_name,
                                        description=file_desc,
                                        content="".join(str_all_list)
                                    )
                                    file_tool.upload_file(file_req, is_notice_fe=False, is_internal_file=False)

            result = "".join(str_all_list) if len(str_all_list) > 0 else "knowledge_tool 执行完成"
            logger.info(f" ==== knowledge_tool recv data: {result} ====")
            return result
        except Exception:
            logger.error(f"{self.context.request_id} knowledge_tool request error")
            logger.error(traceback.format_exc())

        return None


