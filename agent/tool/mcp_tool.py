import json
import traceback

import requests

from agent.tool.base_tool import BaseTool
from config.genie_config import genie_config
from loguru import logger
from http import HTTPStatus


class McpTool(BaseTool):

    def __init__(self, agent_context):
        self.agent_context = agent_context

    @property
    def name(self):
        return "mcp_tool"

    @property
    def desc(self):
        return ""

    @property
    def to_params(self):
        return None

    async def execute(self, obj):
        return None

    def list_tool(self, mcp_server_url):
        try:
            mcp_client_url = genie_config.mcp_client_url + "/v1/tool/list"
            mcp_req = {"server_url": mcp_server_url}
            mcp_res = requests.post(mcp_client_url, json=mcp_req, timeout=30)
            logger.info(f"list tool request: {mcp_req} response: {mcp_res.json()}")
            return json.dumps(mcp_res.json(), ensure_ascii=False)
        except Exception:
            logger.error(f"{self.agent_context.request_id} list tool error")
            logger.error(traceback.format_exc())

    async def call_tool(self, mcp_server_url, tool_name, tool_input):
        try:
            mcp_client_url = genie_config.mcp_client_url + "/v1/tool/call"
            mcp_req = {"name": tool_name, "server_url": mcp_server_url, "arguments": tool_input}
            mcp_res = requests.post(mcp_client_url, json=mcp_req, timeout=30)
            if mcp_res.status_code != HTTPStatus.OK:
                logger.error(f"{self.agent_context.request_id} call tool error")
                return ""

            logger.info(f"call tool request: {mcp_req} response: {mcp_res.json()}")
            return mcp_res
        except Exception:
            logger.error(f"{self.agent_context.request_id} call tool error ")
            logger.error(traceback.format_exc())

        return ""
