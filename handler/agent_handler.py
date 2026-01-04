import json

from agent.entity.enums import ResponseTypeEnum
from config.genie_config import GenieConfig
from model.multi.event_message import EventMessage
from model.protocal import AgentRequest
from model.response.agent_response import AgentResponse, EventResult
from model.response.gpt_process_result import GptProcessResult


class AgentHandler:
    def __init__(self, genie_config: GenieConfig):
        self.genie_config = genie_config

    async def handle(self, context, request):
        """"""
        pass

    def support(self, agent_type):
        """"""
        pass


class AgentResponseHandler:
    def __init__(self):
        pass

    def handle(
            self,
            request: AgentRequest,
            response: AgentResponse,
            agent_resp_list: list,
            event_result: EventResult
    ):
        pass

    def build_incr_result(
            self,
            request: AgentRequest,
            event_result: EventResult,
            agent_response: AgentResponse
    ):
        stream_result = GptProcessResult()
        stream_result.response_type = ResponseTypeEnum.TEXT.value
        stream_result.status = "success" if agent_response.finish else "running"
        stream_result.finished = agent_response.finish

        if "result" == agent_response.message_type:
            stream_result.response = agent_response.result
            stream_result.response_all = agent_response.result
        stream_result.req_id = request.request_id
        agent_type = str(agent_response.result_map["agentType"]) if agent_response.result_map is not None and "agentType" in agent_response.result_map else None
        result_map = dict()
        result_map["agentType"] = agent_type
        result_map["multiAgent"] = dict()
        result_map["eventData"] = dict()

        #增量数据
        message = EventMessage(message_id=agent_response.message_id)
        is_final = (agent_response.is_final == True)
        is_filter_final = (agent_response.result_map is not None) and \
                          (agent_response.message_type == "deep_search") and \
                          ("messageType" in agent_response.result_map) and \
                          (agent_response.result_map["messageType"] == "extend")

        if agent_response.message_type == "plan_thought":
            message.message_type = agent_response.message_type
            message.message_order = event_result.get_and_incr_order(agent_response.message_type)
            message.result_map = agent_response.model_dump(by_alias=True)
            if is_final and "plan_thought" not in event_result.result_map:
                event_result.result_map["plan_thought"] = agent_response.plan_thought
        elif agent_response.message_type == "plan":
            if event_result.is_init_plan():
                message.message_type = agent_response.message_type
                message.message_order = 1
                message.result_map = agent_response.plan.model_dump(by_alias=True)
                if is_final:
                    event_result.result_map["plan"] = agent_response.plan.model_dump(by_alias=True)
            else:
                #plan更新，需要关联task
                message.task_id = event_result.get_task_id()
                message.task_order = event_result.task_order.get_and_increment()
                message.message_type = "task"
                message.message_order = 1
                message.result_map = agent_response.model_dump(by_alias=True)
        elif agent_response.message_type == "task":
            message.task_id = event_result.renew_task_id()
            message.task_order = event_result.task_order.get_and_increment()
            message.message_type = agent_response.message_type
            message.message_order = 1
            message.result_map = agent_response.model_dump(by_alias=True)
            if is_final:
                task = []
                task.append(message.result_map)
                event_result.set_result_map_task(task)
        else:
            message.task_id = event_result.get_task_id()
            message.task_order = event_result.task_order.get_and_increment()
            message.message_type = "task"
            message.message_order = 1
            if agent_response.message_type in event_result.stream_task_message_type:
                order_key = event_result.get_task_id() + ":" + agent_response.message_type
                message.message_order = event_result.get_and_incr_order(order_key)
            message.result_map = agent_response.model_dump(by_alias=True)
            if is_final and not is_filter_final:
                event_result.set_result_map_sub_task(message.result_map)

        #增量缓存
        result_map["eventData"] = message.model_dump(by_alias=True)
        stream_result.result_map = result_map
        return stream_result

