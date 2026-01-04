import asyncio
import contextvars
import json
import threading
from model.protocal import AgentRequest, GptQueryReq
from fastapi import APIRouter
from sse_starlette import ServerSentEvent, EventSourceResponse
from loguru import logger
from config.genie_config import genie_config
from agent.agent.auto_agent import AutoAgent
from service import multi_agent

router = APIRouter()


def handle_output_style(query: str, output_style: str):
    query += genie_config.output_style_prompts_dict.get(output_style, "")
    return query


@router.post("/AutoAgent")
async def auto_agent(request: AgentRequest):
    logger.info(f"{request.request_id} auto agent request: {request}")
    # 拼接输出类型
    request.query = handle_output_style(request.query, request.output_style)
    queue = asyncio.Queue()

    async def _stream(queue):
        while True:
            data = await queue.get()
            if isinstance(data, str):
                if "[DONE]" in data:
                    data = data.replace("[DONE]", "")
                    yield ServerSentEvent(data=data)
            yield ServerSentEvent(data=data)

    def run_task(context, queue, request):
        context.run(lambda: asyncio.run(AutoAgent(queue).run(request)))

    thread = threading.Thread(target=run_task, args=(contextvars.copy_context(), queue, request), daemon=True)
    thread.start()
    return EventSourceResponse(
        _stream(queue),
        ping_message_factory=lambda: ServerSentEvent(data="heartbeat"),
        ping=10
    )


@router.get("/web/health")
def health():
    return "ok"


@router.post("/web/api/v1/gpt/queryAgentStreamIncr")
async def query_agent_stream_incr(request: GptQueryReq):
    return await multi_agent.query_multi_agent_incr_stream(request)
