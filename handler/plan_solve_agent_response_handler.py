import traceback

from loguru import logger

from handler.agent_handler import AgentResponseHandler
from model.protocal import AgentRequest
from model.response.agent_response import AgentResponse, EventResult


class PlanSolveAgentResponseHandler(AgentResponseHandler):
    def handle(
            self,
            request: AgentRequest,
            response: AgentResponse,
            agent_resp_list: list,
            event_result: EventResult
    ):
        try:
            return self.build_incr_result(request, event_result, response)
        except Exception:
            logger.error(f"{request.request_id} PlanSolveAgentResponseHandler handle error")
            logger.error(traceback.format_exc())
            return None