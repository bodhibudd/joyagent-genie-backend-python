import asyncio
import json
import time
import traceback
import httpx
import requests
from loguru import logger
from sse_starlette import ServerSentEvent, EventSourceResponse
from agent.entity.enums import AutoBotsResultStatus, AgentType, ResponseTypeEnum
from handler.plan_solve_agent_response_handler import PlanSolveAgentResponseHandler
from handler.react_agent_response_handler import ReactAgentResponseHandler
from model.protocal import GptQueryReq, AgentRequest
from model.response.agent_response import EventResult, AgentResponse
from model.response.gpt_process_result import GptProcessResult
from util.chat_util import ChatUtils
from config.genie_config import genie_config

handler_map = {
    AgentType.PLAN_SOLVE: PlanSolveAgentResponseHandler(),
    AgentType.REACT: ReactAgentResponseHandler()
}

client = httpx.AsyncClient()


def build_agent_request(request: GptQueryReq):
    agent_req = AgentRequest()
    agent_req.request_id = request.request_id
    agent_req.erp = request.user
    agent_req.query = request.query
    agent_req.agent_type = 5 if request.deep_think == 0 else 3
    agent_req.sop_prompt = genie_config.genie_sop_prompt if agent_req.agent_type == 3 else ""
    agent_req.base_prompt = genie_config.genie_base_prompt if agent_req.agent_type == 5 else ""
    agent_req.is_stream = True
    agent_req.output_style = request.output_style

    return agent_req


def build_heartbeat_data(req_id):
    result = GptProcessResult()
    result.finished = False
    result.status = "success"
    result.response_type = ResponseTypeEnum.TEXT.value
    result.response = ""
    result.response_all = ""
    result.use_times = 0
    result.user_tokens = 0
    result.req_id = req_id
    result.package_type = "heartbeat"
    result.encrypted = False
    return result.model_dump_json(by_alias=True)


async def handle_multi_agent_request(auto_req: AgentRequest, queue):
    url = "http://127.0.0.1:8080/AutoAgent"
    start_time = time.time()
    try:
        async with client.stream("POST", url=url, json=auto_req.model_dump(),
                                 timeout=60) as response:

            if not response.is_success:
                logger.error(f"{auto_req.request_id}, response body is failed: {response}")
                return
            agent_resp_list = list()
            event_result = EventResult()
            async for line in response.aiter_lines():
                if len(line) == 0:
                    continue
                line = line.replace("data: ", "")
                if line.startswith("heartbeat"):
                    result = build_heartbeat_data(auto_req.request_id)
                    await queue.put(result)
                    logger.info(f"{auto_req.request_id} heartbeat-data: {line}")
                    continue
                data = AgentResponse.model_validate_json(line)
                # logger.info(f"{auto_req.request_id} recv from auto controller: {data}")
                agent_type = AgentType(auto_req.agent_type)
                handler = handler_map[agent_type]
                result = handler.handle(auto_req, data, agent_resp_list, event_result)
                if result.finished:
                    logger.info(f"{auto_req.request_id} task total cost time:{time.time() - start_time}ms")
                    await queue.put("[DONE]" + result.model_dump_json(by_alias=True))
                    logger.info("lyz:" + result.model_dump_json(by_alias=True))
                    break
                await queue.put(result.model_dump_json(by_alias=True))
                logger.info(result.model_dump_json(by_alias=True))
    except Exception:
        logger.error(traceback.format_exc())


async def search_for_agent_request(request: GptQueryReq, queue):
    req = build_agent_request(request)
    logger.info(f"{request.request_id} start handle Agent request: {req}")
    try:
        await handle_multi_agent_request(req, queue)
    except Exception as e:
        logger.error(
            f"{request.request_id}, error in requestMultiAgent, deepThink: {request.deep_think}, errorMsg: {str(e)}")
        raise e
    finally:
        logger.info(f"{request.request_id}, agent.query.web.singleRequest end, requestId: {request}")
    return ChatUtils.to_auto_bots_result(request, AutoBotsResultStatus.LOADING.value) # todo,这里不需要组装参数返回，因为上游并没有用到


async def query_multi_agent_incr_stream(request: GptQueryReq):
    queue = asyncio.Queue()

    request.user = "genie"
    request.deep_think = 0 if request.deep_think is None else request.deep_think
    trace_id = ChatUtils.get_request_id(request.user, request.session_id, request.request_id)
    request.trace_id = trace_id

    async def _stream(queue):
        while True:
            data = await queue.get()
            if isinstance(data, str):
                if "[DONE]" in data:
                    data = data.replace("[DONE]", "")
                    yield ServerSentEvent(data=data)
                    break
            yield ServerSentEvent(data=data)

    asyncio.create_task(search_for_agent_request(request, queue))

    return EventSourceResponse(
        _stream(queue)
    )

