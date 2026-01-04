import asyncio
import traceback
from typing import Optional

import requests
from loguru import logger

from agent.entity.code_interpreter_response import FileInfo
from agent.entity.file import FileRequest, File

from config.genie_config import genie_config
from agent.agent.agent_context import AgentContext
from agent.tool.base_tool import BaseTool
from model.response.agent_response import build_stream_response
from util.string_util import remove_special_chars

class FileTool(BaseTool):
    def __init__(
            self,
            context: Optional[AgentContext] = None,
            queue: asyncio.Queue = None
    ):
        self.context = context
        self.queue = queue

    @property
    def name(self):
        return "file_tool"

    @property
    def desc(self):
        desc = "这是一个文件工具，可以上传或下载文件"
        return desc if len(genie_config.file_tool_desc) == 0 else genie_config.file_tool_desc

    @property
    def to_params(self):
        if len(genie_config.file_tool_desc) != 0:
            return genie_config.file_tool_params
        parameters = dict()
        parameters["type"] = "object"
        parameters["properties"] = {
            "command": {"type": "string", "description": "文件操作类型：upload、get"},
            "filename": {"type": "string", "description": "文件名"},
            "description": {"type": "string", "description": "文件描述，20字左右，upload时必填"},
            "content": {"type": "string", "description": "文件内容，upload时必填"},
        }
        parameters["required"] = ["command", "filename"]
        return parameters

    async def execute(self, obj):
        try:
            command = obj.get("command", "")
            file_req = FileRequest(
                request_id=self.context.request_id,
                file_name = obj.get("filename", ""),
                description = obj.get("description", ""),
                content = obj.get("content", "")
            )
            if "upload" == command:
                return await self.upload_file(file_req, True, False)
            elif "get" == command:
                return await self.get_file(file_req, True)
        except Exception:
            logger.error(f"{self.context.request_id} file tool error")
            logger.error(traceback.format_exc())
        return None

    async def upload_file(
            self,
            file_req: FileRequest,
            is_notice_fe: bool,
            is_internal_file: bool
    ):
        #多轮对话替换requestid为sessionid
        file_req.request_id = self.context.session_id
        file_req.file_name = remove_special_chars(file_req.file_name)
        if len(file_req.file_name) == 0:
            logger.error(f"{self.context.request_id} 上传文件失败 文件名为空")
            return None
        url = genie_config.code_interpreter_url + "/v1/file_tool/upload_file"
        try:
            response = requests.post(url, json=file_req.model_dump(by_alias=True), timeout=(60,300))
            if not response.ok or response.json() is None:
                logger.error(f"{self.context.request_id} upload file faied")
                return None
            file_res = response.json()
            logger.info(f"{self.context.request_id} file tool upload response {file_res}")
            #构造前端格式
            result_map = dict()
            result_map["command"] = "写入文件"
            file_info = list()
            file_info.append(FileInfo(
                file_name=file_req.file_name,
                oss_url=file_res["ossUrl"],
                domain_url=file_res["domainUrl"],
                file_size=file_res["fileSize"]
            ).model_dump(by_alias=True))
            result_map["fileInfo"] = file_info
            # 数字人
            digital_employee = self.context.tool_collection.get_digital_employee(self.name)
            logger.info(f"requestId:{self.context.request_id} task:{self.context.tool_collection.current_task} toolName:{self.name} digitalEmployee:{digital_employee}")
            # 添加文件到上下文
            file = File(
                oss_url=file_res["ossUrl"],
                domain_url=file_res["domainUrl"],
                file_name=file_req.file_name,
                file_size=file_res["fileSize"],
                description=file_req.description,
                is_internal_file=is_internal_file
            )
            self.context.product_files.append(file.model_dump(by_alias=True))
            if is_notice_fe:
                #内部文件不通知前端
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "file",
                    result_map,
                    digital_employee,
                    True
                )
                await self.queue.put(data)
            if not is_internal_file:
                # 非内部文件，参与交付物
                self.context.task_product_files.append(file.model_dump(by_alias=True))
            #返回工具执行结果
            return file_req.file_name + "写入到文件链接: "+ file_res["ossUrl"]
        except Exception as e:
            logger.error(f"{self.context.request_id} upload file error")
            logger.error(traceback.format_exc())
        return None

    async def get_file(
            self,
            file_req: FileRequest,
            is_notice_fe: bool
    ):
        url = genie_config.code_interpreter_url + "/v1/file_tool/get_file"
        req = FileRequest(
            requestId=self.context.session_id,
            fileName=file_req.file_name
        )
        try:
            logger.info(f"{self.context.request_id} file tool get request {req}")
            response = requests.post(url, json=req.model_dump(by_alias=True), timeout=(60, 300))
            if not response.ok or response.json() is None:
                err_msg = "获取文件失败"+file_req.file_name
                logger.error(err_msg)
                return err_msg
            file_res = response.json()
            logger.info(f"{self.context.request_id} file tool get response {file_res}")
            # 构造前端格式
            result_map = dict()
            result_map["command"] = "读取文件"
            file_info = list()
            file_info.append(FileInfo(
                file_name=file_req.file_name,
                oss_url=file_res["ossUrl"],
                domain_url=file_res["domainUrl"]
            ).model_dump(by_alias=True))
            result_map["fileInfo"] = file_info
            # 获取数字人
            digital_employee = self.context.tool_collection.get_digital_employee(self.name)
            logger.info(
                f"requestId:{self.context.request_id} task:{self.context.tool_collection.current_task} toolName:{self.name} digitalEmployee:{digital_employee}")
            # 通知前端
            if is_notice_fe:
                data = build_stream_response(
                    self.context.request_id,
                    self.context.agent_type,
                    None,
                    "file",
                    result_map,
                    digital_employee,
                    True
                )
                await self.queue.put(data)
            file_content = self.get_url_content(file_res["ossUrl"])
            if file_content is not None:
                if len(file_content) > genie_config.file_tool_content_truncate_len:
                    file_content = file_content[: genie_config.file_tool_content_truncate_len]
                return "文件内容 " + file_content
        except Exception:
            logger.error(f"{self.context.request_id} get file error")
        return None

    def get_url_content(self, url):
        try:
            response = requests.get(url, timeout=(60,300))
            if not response.ok or response.text is None:
                err_msg = f"{self.context.request_id} 获取文件失败, 状态码:{response.status_code}"
                logger.error(err_msg)
                return None
            else:
                return response.text
        except Exception:
            logger.error(f"{self.context.request_id} 获取文件异常")
            logger.error(traceback.format_exc())
            return None



