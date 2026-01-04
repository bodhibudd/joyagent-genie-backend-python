import asyncio
import json
import traceback
from typing import Optional

import requests
from loguru import logger

from agent.agent.agent_context import AgentContext
from agent.entity.file import File
from agent.entity.code_interpreter_request import CodeInterpreterRequest
from agent.entity.code_interpreter_response import CodeInterpreterResponse
from agent.tool.base_tool import BaseTool
from config.genie_config import genie_config
from model.response.agent_response import build_stream_response


class CodeInterpreterTool(BaseTool):
    def __init__(
            self,
            context: Optional[AgentContext] = None,
            queue: Optional[asyncio.Queue] = None
    ):
        self.context = context
        self.queue = queue

    @property
    def name(self):
        return "code_interpreter"

    @property
    def desc(self):
        desc = "这是一个代码工具，可以通过编写代码完成数据处理、数据分析、图表生成等任务"
        return desc if len(genie_config.code_agent_desc) == 0 else genie_config.code_agent_desc

    @property
    def to_params(self):
        if genie_config.code_agent_params:
            return genie_config.code_agent_params

        parameters = dict()
        parameters["type"] = "object"
        parameters["properties"] = {
            "task": {"type": "string", "description": "需要完成的任务以及完成任务需要的数据，需要尽可能详细"},
        }
        parameters["required"] = ["task"]

        return parameters

    async def execute(self, obj):
        try:
            task = obj.get("task", "")
            file_names = list()
            for file in self.context.product_files:
                file = File.model_validate_json(json.dumps(file, ensure_ascii=False))
                file_names.append(file.file_name)
            code_req = CodeInterpreterRequest(
                request_id=self.context.request_id,
                query=self.context.query,
                task=task,
                file_names=file_names,
                stream=True
            )
            result = await self.call_code_agent_stream(code_req)
            return result
        except Exception as e:
            logger.error(f"{self.context.request_id} code agent error")
            logger.error(traceback.format_exc())
        return None

    async def call_code_agent_stream(
            self,
            code_req: CodeInterpreterRequest
    ):
        try:
            url = genie_config.code_interpreter_url + "/v1/tool/code_interpreter"
            logger.info(f"{code_req.request_id} code_interpreter request {code_req}")
            with requests.post(url, json=code_req.model_dump(by_alias=True), stream=True, timeout=(60,300)) as response:

                logger.info(f"{self.context.request_id} code_interpreter_tool response {response} {response.status_code}")
                code_res = CodeInterpreterResponse(
                    code_output="code_interpreter执行失败" # 默认输出
                )
                if not response.ok:
                    logger.error(f"{code_req.request_id} code_interpreter request error")
                    raise Exception(f"Unexpected response code: {response.status_code}")
                for line in response.iter_lines():
                    if line is None:
                        continue
                    line = line.decode("utf8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if "[DONE]" == data:
                            break
                        if data.startswith("heartbeat"):
                            continue
                        logger.info(f"{self.context.request_id} code_interpreter recv data: {data}")
                        code_res = CodeInterpreterResponse.model_validate_json(data)
                        if code_res.file_info:
                            for file_info in code_res.file_info:
                                file = File(
                                    file_name=file_info.file_name,
                                    file_size=file_info.file_size,
                                    oss_url=file_info.oss_url,
                                    domain_url=file_info.domain_url,
                                    description=file_info.file_name,
                                    is_internal_file=False
                                )
                                self.context.product_files.append(file.model_dump(by_alias=True))
                                self.context.task_product_files.append(file.model_dump(by_alias=True))
                        # 数字人
                        digital_employee = self.context.tool_collection.get_digital_employee(self.name)
                        logger.info(
                            f"requestId:{self.context.request_id} task:{self.context.tool_collection.current_task} "
                            f"toolName:{self.name} digitalEmployee:{digital_employee}"
                        )
                        data = build_stream_response(
                            self.context.request_id,
                            self.context.agent_type,
                            None,
                            "code",
                            code_res.model_dump(by_alias=True),
                            digital_employee,
                            True
                        )
                        await self.queue.put(data)

            output = list()
            if code_res.code_output:
                output.append(code_res.code_output)
            else:
                logger.error(f"code_res: {code_res}")
            if code_res.file_info is not None and len(code_res.file_info) != 0:
                output.append("\n\n其中保存了文件: ")
                for file_info in code_res.file_info:
                    output.append(file_info.file_name)
            return "\n".join(output)
        except Exception as e:
            logger.error(f"{self.context.request_id} code_interpreter request error")
            raise Exception(str(e))

        return


