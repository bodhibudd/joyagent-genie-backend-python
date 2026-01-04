import asyncio
import json
import traceback
import uuid

import requests
from loguru import logger

from agent.entity.file import File

from agent.entity.code_interpreter_request import CodeInterpreterRequest
from agent.entity.code_interpreter_response import CodeInterpreterResponse
from agent.tool.base_tool import BaseTool
from agent.agent.agent_context import AgentContext
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response


class ReportTool(BaseTool):
    def __init__(
            self,
            context: AgentContext,
            queue: asyncio.Queue = None
    ):
        self.context = context
        self.queue = queue

    @property
    def name(self):
        return "report_tool"

    @property
    def desc(self):
        desc = "这是一个报告工具，可以通过编写HTML、MarkDown报告"
        return genie_config.report_tool_desc if len(genie_config.report_tool_desc) != 0 else desc

    @property
    def to_params(self):
        if genie_config.report_tool_params:
            return genie_config.report_tool_params

        task_params = {"type": "string", "description": "需要完成的任务以及完成任务需要的数据，需要尽可能详细"}
        properties = {"task": task_params}
        parameters = {"type": "object", "properties": properties, "required": ["task"]}
        return parameters

    async def execute(self, obj):
        try:
            task = obj.get("task", "")
            file_description = obj.get("fileDescription", "")
            file_name = obj.get("fileName", "")
            file_type = obj.get("fileType", "")
            if len(file_name) == 0:
                logger.error(f"{self.context.request_id} 文件名参数为空，无法生成报告。")
                return None

            file_names = list()
            for file in self.context.product_files:
                file = File.model_validate_json(json.dumps(file, ensure_ascii=False))
                file_names.append(file.file_name)
            stream_mode = dict()
            stream_mode["mode"] = "token"
            stream_mode["token"] = 10
            request = CodeInterpreterRequest(
                request_id=self.context.request_id,
                query=self.context.query,
                task=task,
                file_names=file_names,
                file_name=file_name,
                file_description=file_description,
                stream=True,
                content_stream=self.context.is_stream,
                stream_mode=stream_mode,
                file_type=file_type,
                template_type=self.context.template_type
            )
            res = await self.call_code_agent_stream(request)
            return res
        except Exception:
            logger.error(f"{self.context.request_id} report_tool error")
            logger.error(traceback.format_exc())
        return None

    async def call_code_agent_stream(
            self,
            code_req: CodeInterpreterRequest
    ):
        url = genie_config.code_interpreter_url + "/v1/tool/report"
        intervals = genie_config.message_interval.get("llm", "1,3").split(",")
        first_interval = int(intervals[0])
        send_interval = int(intervals[1])
        index = 1
        message_id = str(uuid.uuid4())
        digital_employee = self.context.tool_collection.get_digital_employee(self.name)
        try:
            with requests.post(url, json=code_req.model_dump(by_alias=True), stream=True, timeout=(60,600)) as response:
                logger.info(f"{self.context.request_id} report_tool response {response} {response.status_code}")
                if response.raw is None or response.content is None:
                    logger.error(f"{code_req.request_id} report_tool request error")
                    return
                if not response.ok:
                    logger.error(f"{code_req.request_id} report_tool request error")
                    return
                str_incr = list()
                for line in response.iter_lines():
                    if line is None:
                        continue
                    line = line.decode("utf8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if "[DONE]" == data:
                            break
                        if index == 1 or index % 100 == 0:
                            logger.info(f"{self.context.request_id} report_tool recv data: {data}")
                        if data.startswith("heartbeat"):
                            continue
                        code_res = CodeInterpreterResponse.model_validate_json(data)
                        if code_res.is_final:
                            #report_tool只会输出一个文件，使用模型输出的文件名和描述
                            if not code_res.file_info:
                                for file_info in code_res.file_info:
                                    file = File(
                                        file_name=code_req.file_name,
                                        file_size=file_info.file_size,
                                        oss_url=file_info.oss_url,
                                        domain_url=file_info.domain_url,
                                        description=code_req.file_description,
                                        is_internal_file=False
                                    )
                                    self.context.product_files.append(file.model_dump(by_alias=True))
                                    self.context.task_product_files.append(file.model_dump(by_alias=True))
                            data = build_stream_response(
                                self.context.request_id,
                                self.context.agent_type,
                                message_id,
                                code_req.file_type,
                                code_res.model_dump(by_alias=True),
                                digital_employee,#数字人
                                True
                            )
                            await self.queue.put(data)
                        else:
                            str_incr.append(code_res.data)
                            if index == first_interval or index % send_interval == 0:
                                code_res.data = "".join(str_incr)
                                data = build_stream_response(
                                    self.context.request_id,
                                    self.context.agent_type,
                                    message_id,
                                    code_req.file_type,
                                    code_res.model_dump(by_alias=True),
                                    digital_employee,# 数字人
                                    False
                                )
                                await self.queue.put(data)
                                str_incr.clear()
                        index += 1
        except Exception:
            logger.error(f"{self.context.request_id} report_tool request error")
            logger.error(traceback.format_exc())
            return

        result = code_res.data if code_res.data is not None and len(code_res.data) != 0 else code_res.code_output
        return result




