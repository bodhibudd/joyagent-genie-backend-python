import asyncio
import json
import uuid
from typing import Optional

import requests
from loguru import logger

from agent.agent.agent_context import AgentContext
from agent.entity.file import FileRequest
from agent.entity.deep_search_request import DeepSearchRequest
from agent.entity.deep_search_response import DeepSearchResponse
from agent.tool.base_tool import BaseTool
from agent.tool.common.file_tool import FileTool
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response
from util.string_util import remove_special_chars


class DeepSearchTool(BaseTool):
    def __init__(
            self,
            context: Optional[AgentContext] = None,
            queue: Optional[asyncio.Queue] = None
    ):
        self.context = context
        self.queue = queue

    @property
    def name(self):
        return "deep_search"

    @property
    def desc(self):
        desc = "这是一个搜索工具，可以通过搜索内外网知识"
        return genie_config.deep_search_tool_desc if len(genie_config.deep_search_tool_desc) != 0 else desc

    @property
    def to_params(self):
        if genie_config.deep_search_params:
            return genie_config.deep_search_params

        parameters = dict()
        parameters["type"] = "object"
        parameters["properties"] = {
            "query": {"type": "string", "description": "需要搜索的query"}
        }
        parameters["required"] = ["query"]

        return parameters

    async def execute(self, obj):
        query = obj.get("query", "")
        src_config = dict()
        bing_config = dict()
        bing_config["count"] = genie_config.deep_search_page_count
        src_config["bing"] = bing_config
        deep_req = DeepSearchRequest(
            request_id=self.context.request_id,
            query=query,
            agent_id="1",
            scene_type="auto_agent",
            src_configs=src_config,
            stream=True,
            content_stream=self.context.is_stream
        )
        result = await self.call_deep_search_stream(deep_req)
        return result

    async def call_deep_search_stream(
            self,
            deep_req: DeepSearchRequest
    ):
        try:
            url = genie_config.deep_search_url + "/v1/tool/deepsearch"
            logger.info(f"{self.context.request_id} deep_search request {deep_req}")
            intervals = genie_config.message_interval.get("llm", "1,3").split(",")
            first_interval = int(intervals[0])
            send_interval = int(intervals[1])
            index = 1
            with requests.post(url, json=deep_req.dict(), stream=True, timeout=(60,300)) as response:
                logger.info(f"{self.context.request_id} deep_search response {response} {response.status_code}")
                if not response.ok:
                    logger.error(f"{deep_req.request_id} deep_search request error")
                    raise Exception(f"Unexpected response code: {response.status_code}")
                str_incr = list()
                str_all = list()
                digital_employee = self.context.tool_collection.get_digital_employee(self.name)
                result = "搜索结果为空" #默认输出
                message_id = ""
                for line in response.iter_lines():
                    if line is None:
                        continue
                    line = line.decode("utf8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if "[DONE]" == data:
                            break
                        if index == 1 or index % 100 == 0:
                            logger.info(f"{self.context.request_id} deep_search recv data: {data}")
                        if data.startswith("heartbeat"):
                            continue
                        search_res = DeepSearchResponse.model_validate_json(data)
                        file_tool = FileTool(self.context)
                        # 上传搜索内容到文件中
                        if search_res.is_final:
                            if self.context.is_stream:
                                search_res.answer = "".join(str_all)
                            if search_res.answer is None or len(search_res.answer) == 0:
                                logger.error(f"{self.context.request_id} deep search answer empty")
                                break
                            file_name = remove_special_chars(search_res.query + "的搜索结果.md")
                            file_desc = search_res.answer[:min(len(search_res.answer), genie_config.deep_search_tool_file_desc_truncate_len)]
                            file_req = FileRequest(
                                request_id=self.context.request_id,
                                file_name=file_name,
                                description=file_desc,
                                content=search_res.answer
                            )
                            await file_tool.upload_file(file_req, False, False)
                            result = search_res.answer[:min(len(search_res.answer), genie_config.deep_search_tool_file_desc_truncate_len)]
                            data = build_stream_response(
                                self.context.request_id,
                                self.context.agent_type,
                                message_id,
                                "deep_search",
                                search_res.model_dump(by_alias=True),
                                digital_employee,
                                True
                            )
                            await self.queue.put(data)
                        else:
                            content_map = dict()
                            for idx, search_query in enumerate(search_res.search_result.query):
                                content_map[search_query] = search_res.search_result.docs[idx]

                            if "extend" == search_res.message_type:
                                message_id = str(uuid.uuid4())
                                search_res.search_finish = False
                                data = build_stream_response(
                                    self.context.request_id,
                                    self.context.agent_type,
                                    message_id,
                                    "deep_search",
                                    search_res.model_dump(by_alias=True),
                                    digital_employee,
                                    True
                                )
                                await self.queue.put(data)
                            elif "search" == search_res.message_type:
                                search_res.search_finish = True
                                data = build_stream_response(
                                    self.context.request_id,
                                    self.context.agent_type,
                                    message_id,
                                    "deep_search",
                                    search_res.model_dump(by_alias=True),
                                    digital_employee,
                                    True
                                )
                                await self.queue.put(data)
                                file_req = FileRequest(
                                    request_id=self.context.request_id,
                                    file_name=search_res.query + "_search_result.txt",
                                    description=search_res.query + "...",
                                    content= json.dumps(content_map, ensure_ascii=False)
                                )
                                await file_tool.upload_file(file_req, False, True)
                            elif "report" == search_res.message_type:
                                if index == 1:
                                    message_id = str(uuid.uuid4())
                                str_incr.append(search_res.answer)
                                str_all.append(search_res.answer)
                                if index == first_interval or index % send_interval == 0:
                                    search_res.answer = "".join(str_incr)
                                    str_incr.clear()
                                    data = build_stream_response(
                                        self.context.request_id,
                                        self.context.agent_type,
                                        message_id,
                                        "deep_search",
                                        search_res.model_dump(by_alias=True),
                                        digital_employee,
                                        False
                                    )
                                    await self.queue.put(data)
                                index += 1
                return result

        except Exception as e:
            logger.error(f"{self.context.request_id} deep_search request error")
            raise e
        return None
