from typing import Optional, List

from pydantic import BaseModel

from agent.tool.base_tool import BaseTool
from config.genie_config import genie_config


class PlanningPrompt:
    SYSTEM_PROMPT = "\n{{sopPrompt}}\n\n===\n# 环境变量\n## 当前日期\n{{date}}\n\n# 当前可用的文件名及描述\n{{files}}\n\n# 约束\n- 思考过程中，不要透露你的工具名称\n- 调用planning生成任务列表，完成所有子任务就能完成任务。\n- 以上是你需要遵循的指令。\n\nLet's think step by step (让我们一步步思考)\n"
    NEXT_STEP_PROMPT = "工具planing的参数有\n必填参数1：命令command\n可选参数2：当前步状态step_status。\n\n必填参数1：命令command的枚举值有：\n'mark_step', 'finish'\n含义如下：\n- 'finish' 根据已有的执行结果，可以判断出任务已经完成，输出任务结束，命令command为：finish\n- 'mark_step' 标记当前任务规划的状态，设置当前任务的step_status\n\n当参数command值为mark_step时，需要可选参数2step_status，其中当前步状态step_status的枚举值如下：\n- 没有开始'not_started'\n- 进行中'in_progress' \n- 已完成'completed'\n\n对应如下几种情况：\n1.当前任务是否执行完成，完成以及失败都算执行完成，执行完成将入参step_status设置为`completed`\n\n一步一步分析完成任务，确定工具planing的入参，调用planing工具"


class Plan(BaseModel):
    title: Optional[str] = None,
    steps: Optional[List[str]] = None,
    step_status: Optional[List[str]] = None,
    notes: Optional[List[str]] = None

    @classmethod
    def create(cls, title: str, steps: List[str]):
        """创建计划"""
        status = list()
        notes = list()
        for step in steps:
            status.append("not_started")
            notes.append("")
        return Plan(title=title, steps=steps, step_status=status, notes=notes)

    def update(self, title: str, new_steps):
        """更新计划"""
        if title is not None:
            self.title = title
        if new_steps is not None:
            new_statuses = list()
            new_notes = list()
        for i, new_step in enumerate(new_steps):
            if i < len(self.steps) and new_step == self.steps[i]:
                # 保持原有状态和备注
                new_statuses.append(self.step_status[i])
                new_notes.append(self.notes[i])
            else:
                new_statuses.append("not_started")
                new_notes.append("")

        self.steps = new_steps
        self.step_status = new_statuses
        self.notes = new_notes

    def update_step_status(self, step_index, status, note):
        """更新步骤状态"""
        if step_index < 0 or step_index >= len(self.steps):
            raise Exception("Invalid step index: " + str(step_index))
        if status is not None:
            self.step_status[step_index] = status
        if note is not None:
            self.notes[step_index] = note

    def get_current_step(self):
        for i, step in enumerate(self.steps):
            if "in_progress" == self.step_status[i]:
                return self.steps[i]
        return ""

    def step_plan(self):
        """更新当前task为completed， 下一个task为in_progress"""
        if len(self.steps) == 0:
            return
        if len(self.get_current_step()) == 0:
            self.update_step_status(0, "in_progress", "")
            return

        for i, step in enumerate(self.steps):
            if "in_progress" == self.step_status[i]:
                self.update_step_status(i, "completed", "")
                if (i + 1) < len(self.steps):
                    self.update_step_status(i+1, "in_progress", "")
                    break


class PlanningTool(BaseTool):
    def __init__(self):
        self.__command_handlers = dict()
        self.__command_handlers["create"] = self._create_plan
        self.__command_handlers["update"] = self._update_plan
        self.__command_handlers["mark_step"] = self._mark_step
        self.__command_handlers["finish"] = self._finish_plan
        self.plan= None

    @property
    def name(self):
        return "planning"

    @property
    def desc(self):
        desc = "这是一个计划工具，可让代理创建和管理用于解决复杂任务的计划。\n该工具提供创建计划、更新计划步骤和跟踪进度的功能。\n使用中文回答"
        return desc if len(genie_config.plan_tool_desc) == 0 else genie_config.plan_tool_desc

    @property
    def to_params(self):
        if genie_config.plan_tool_params:
            return genie_config.plan_tool_params
        return self._parameters()

    def _parameters(self):
        parameters = dict()
        parameters["type"] = "object"
        parameters["properties"] = self._properties()
        parameters["required"] = ["command"]
        return parameters

    def _properties(self):
        properties = dict()
        properties["command"] = {
            "type": "string",
            "enum": ["create", "update", "mark_step", "finish"],
            "description": "The command to execute. Available commands: create, update, mark_step, finish"
        }
        properties["title"] = {
            "type": "string",
            "description": "Title for the plan. Required for create command, optional for update command."
        }
        properties["steps"] = {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of plan steps. Required for create command, optional for update command."
        }
        properties["step_index"] = {
            "type": "integer",
            "description": "Index of the step to update (0-based). Required for mark_step command."
        }
        properties["step_status"] = {
            "type": "string",
            "enum": ["not_started", "in_progress", "completed", "blocked"],
            "description": "Status to set for a step. Used with mark_step command."
        }
        properties["step_notes"] = {
            "type": "string",
            "description": "Additional notes for a step. Optional for mark_step command."
        }

    async def execute(self, obj):
        if not isinstance(obj, dict):
            raise Exception("Input must be a dict")
        command = obj.get("command", None)
        if command is None or len(command) == 0:
            raise Exception("Command is required")
        handler = self.__command_handlers.get(command, None)
        if handler is None:
            raise Exception("Unknown command: " + command)

        return handler(obj)

    def _create_plan(self, params):
        title = params.get("title", None)
        steps = params.get("steps", None)
        if title is None or steps is None:
            raise Exception("title, and steps are required for create command")

        if self.plan is not None:
            raise Exception("A plan already exists. Delete the current plan first.")

        self.plan = Plan.create(title, steps[:1]) # todo,待去掉
        return "我已创建plan"

    def _update_plan(self, params):
        title = params.get("titles", None)
        steps = params.get("steps", None)
        if self.plan is None:
            raise Exception("No plan exists. Create a plan first.")
        self.plan.update(title, steps)
        return "我已更新plan"

    def _mark_step(self, params):
        step_index = params.get("step_index", None)
        step_status = params.get("step_status", None)
        step_notes = params.get("step_notes", None)
        if self.plan is None:
            raise Exception("No plan exists. Create a plan first.")
        if step_index is None:
            raise Exception("step_index is required for mark_step command")
        self.plan.update_step_status(step_index, step_status, step_notes)

        return f"我已标记plan {step_index} 为 {step_status}"

    def _finish_plan(self, params):
        if self.plan is None:
            self.plan = Plan()
        else:
            for step_index, step in enumerate(self.plan.steps):
                self.plan.update_step_status(step_index, "completed", "")

        return "我已更新plan为完成状态"

    def step_plan(self):
        self.plan.step_plan()
