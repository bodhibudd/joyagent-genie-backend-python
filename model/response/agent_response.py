import json
import re
import time
import traceback
import uuid
import threading
from typing import Optional, List
from loguru import logger
from pydantic import BaseModel, Field


class Plan(BaseModel):
    title: Optional[str] = None
    stages: Optional[List[str]] = None
    steps: Optional[List[str]] = None
    step_status: Optional[List[str]] = Field(None, alias="stepStatus")
    notes: Optional[List[str]] = None

    class Config:
        populate_by_name = True


class ToolResult(BaseModel):
    tool_name: Optional[str] = Field(None, alias="toolName")
    tool_params: Optional[dict] = Field(None, alias="toolParam")
    tool_result: Optional[str] = Field(None, alias="toolResult")

    class Config:
        populate_by_name = True


class AgentResponse(BaseModel):
    request_id: Optional[str] = Field(None, alias="requestId")
    message_id: Optional[str] = Field(None, alias="messageId")
    is_final: bool = Field(False, alias="isFinal")
    message_type: Optional[str] = Field(None, alias="messageType")
    digital_employee: Optional[str] = Field(None, alias="digitalEmployee")
    message_time: Optional[str] = Field(None, alias="messageTime")
    plan_thought: Optional[str] = Field(None, alias="planThought")
    plan: Optional[Plan] = None
    task: Optional[str] = None
    task_summary: Optional[str] = Field(None, alias="taskSummary")
    tool_thought: Optional[str] = Field(None, alias="toolThought")
    tool_result: Optional[ToolResult] = Field(None, alias="toolResult")
    result_map: Optional[dict] = Field(None, alias="resultMap")
    result: Optional[str] = None
    finish: Optional[bool] = False
    ext: Optional[dict] = None

    class Config:
        populate_by_name = True


def format_steps(plan: Plan):
    new_plan = Plan(
        title=plan.title,
        stages=[],
        steps=[],
        step_status=[],
        notes=[]
    )
    pattern = re.compile(r"执行顺序(\d+)\.\s?([\w\W]*)\s?[：:](.*)")
    for i, step in enumerate(plan.steps):
        new_plan.step_status.append(plan.step_status[i])
        new_plan.notes.append(plan.notes[i])
        match = pattern.search(step)
        if match:
            new_plan.steps.append(match.group(3).strip())
            new_plan.stages.append(match.group(2).strip())
        else:
            new_plan.steps.append(step)
            new_plan.stages.append("")
    return new_plan


def build_stream_response(
        request_id: str,
        agent_type: int,
        message_id: str,
        message_type: str,
        message: str | dict,
        digital_employee: str,
        is_final: bool
):
    """组装流式输出返回值"""
    try:
        if message_id is None:
            message_id = str(uuid.uuid4())
        logger.info(f"{request_id} sse send {message_type} {message} {digital_employee}")
        finish = ("result" == message_type)
        result_map = dict()
        result_map["agentType"] = agent_type
        response = AgentResponse()
        response.request_id = request_id
        response.message_id = message_id
        response.message_type = message_type
        response.message_time = str(int(time.time() * 1000))
        response.result_map = result_map
        response.finish = finish
        response.is_final = is_final
        if digital_employee is not None:
            response.digital_employee = digital_employee

        # 为不同类型的消息类型设置返回值参数
        if message_type == "tool_thought":
            response.tool_thought = message
        elif message_type == "task":
            response.task = re.sub(r"^执行顺序(\d+)\.\s?", message, "")
        elif message_type == "task_summary":
            summary = message["taskSummary"]
            response.result_map = message
            response.task_summary = summary
        elif message_type == "plan_thought":
            response.plan_thought = message
        elif message_type == "plan":
            plan = Plan(**message)
            response.plan = format_steps(plan)
        elif message_type == "tool_result":
            response.tool_result = ToolResult(**message)
        elif message_type == "agent_stream":
            response.result = message
        elif message_type == "result":
            if isinstance(message, str):
                response.result = message
            elif isinstance(message, dict):
                summary = message["taskSummary"]
                response.result_map = message
                response.task_summary = summary
            else:
                task_result = message.model_dump(by_alias=True)
                response.result_map = task_result
                response.result = task_result["taskSummary"]
            response.result_map["agentType"] = agent_type
        elif message_type in ["browser", "code", "html", "markdown", "ppt", "file", "knowledge", "deep_search",
                              "data_analysis"]:
            response.result_map = message
            response.result_map["agentType"] = agent_type

        return response.model_dump_json()

    except Exception:
        logger.error("sse send error " + traceback.format_exc())
        return None


class AtomicInteger:
    def __init__(self, value=0):
        self._value = value
        self._lock = threading.Lock()

    def increment_and_get(self):
        with self._lock:
            self._value += 1
            return self._value

    def get_and_increment(self):
        with self._lock:
            val = self._value
            self._value += 1
            return val

    def add_and_get(self, delta):
        with self._lock:
            self._value += delta
            return self._value

    def get(self):
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = value


class EventResult:
    def __init__(
            self,
            init_plan: Optional[bool] = None
    ):
        self.init_plan = init_plan
        self.message_count = AtomicInteger(0)
        self.order_mapping = dict()
        self.task_id = None
        self.task_order = AtomicInteger(1)
        self.result_map = dict()
        self.result_list = list()

    def get_and_incr_order(self, key):
        order = self.order_mapping.get(key, None)
        if order is None:
            self.order_mapping[key] = 1
            return 1
        self.order_mapping[key] = order + 1
        return order + 1

    def is_init_plan(self):
        if self.init_plan is None or self.init_plan == False:
            self.init_plan = True
            return True
        return False

    def get_task_id(self):
        if self.task_id is None or len(self.task_id) == 0:
            self.task_id = str(uuid.uuid4())
        return self.task_id

    def renew_task_id(self):
        self.task_order.set(1)
        self.task_id = str(uuid.uuid4())
        return self.task_id

    @property
    def stream_task_message_type(self):
        return ["html", "markdown", "deep_search", "tool_thought", "data_analysis"]

    def get_result_map_task(self):
        if "tasks" in self.result_map:
            obj = self.result_map["tasks"]
            return obj
        return None

    def set_result_map_task(self, task: list):
        tasks = self.get_result_map_task()
        if tasks is None:
            tasks = [task]
            self.result_map["tasks"] = tasks
            return
        tasks.append(task)

    def set_result_map_sub_task(self, sub_task):
        tasks = self.get_result_map_task()
        if tasks is None:
            tasks = [[]]
            self.result_map["tasks"] = tasks
        sub_tasks = tasks[-1]
        sub_tasks.append(sub_task)
