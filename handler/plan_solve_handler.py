import json

from agent.agent.executor_agent import ExecutorAgent
from agent.agent.planning_agent import PlanningAgent
from agent.agent.summary_agent import SummaryAgent
from handler.agent_handler import AgentHandler
from config.genie_config import GenieConfig
from model.response.agent_response import build_stream_response
from service.sop_recall import SopRecall
from agent.agent.agent_context import AgentContext
from loguru import logger
import traceback
from agent.entity.enums import AgentType, AgentState
from model.protocal import AgentRequest


class PlanSolveHandler(AgentHandler):
    def __init__(self, genie_config: GenieConfig):
        self.genie_config = genie_config
        self.sop_recall = SopRecall(genie_config)

    async def handle(self, context: AgentContext, request: AgentRequest):
        self._handle_sop_recall(context, request)
        planning = PlanningAgent(context=context)
        executor = ExecutorAgent(context=context)
        summary = SummaryAgent(context=context)
        summary.system_prompt = summary.system_prompt.replace("{{query}}", request.query)
        planning_result = await planning.run(request.query)
        step_idx = 0
        while step_idx <= self.genie_config.planner_max_steps:
            # todo 任务并非是由<sep>进行切分的，所以这里应该是多余的，planning_results中元素只有一个，也就不需要多个executor,所以下面的else并未实现
            planning_results = ["你的任务是："+task for task in planning_result.split("<sep>")]
            context.task_product_files.clear()
            # if len(planning_results) == 1:
            executor_result = await executor.run(planning_results[0])
            # else:
            planning_result = await planning.run(executor_result)
            if "finish" == planning_result:
                # 任务成功结束，总结任务
                result = summary.summary_task_result(executor.memory.messages, request.query)
                task_result = dict()
                task_result["taskSummary"] = result.task_summary
                if result.files is None or len(result.files) == 0:
                    if context.product_files is not None and len(context.product_files) != 0:
                        file_res = context.product_files
                        #过滤中间搜索结果文件
                        file_res = [file for file in file_res if not file.get("is_internal_file", None)]
                        task_result["fileList"] = reversed(file_res)
                else:
                    task_result["fileList"] = result.files

                data = build_stream_response(
                    context.request_id,
                    context.agent_type,
                    None,
                    "result",
                    task_result,
                    None,
                    True
                )
                await context.queue.put("[DONE]"+data)
                break

            if planning.state == AgentState.IDLE or executor.state == AgentState.IDLE:
                data = build_stream_response(
                    context.request_id,
                    context.agent_type,
                    None,
                    "result",
                    "达到最大迭代次数，任务终止。",
                    None,
                    True
                )
                await context.queue.put("[DONE]"+data)
                break

            if planning.state == AgentState.ERROR or executor.state == AgentState.ERROR:
                data = build_stream_response(
                    context.request_id,
                    context.agent_type,
                    None,
                    "result",
                    "任务执行异常，请联系管理员，任务终止。",
                    None,
                    True
                )
                await context.queue.put("[DONE]"+data)
                break
            step_idx += 1

        return data

    def support(self, agent_type):
        return AgentType.PLAN_SOLVE.value == agent_type

    def _handle_sop_recall(self, agent_context: AgentContext, request):
        try:
            logger.info(f"{request.request_id} 开始执行SOP召回")
            sop_res = self.sop_recall.sop_recall(request.request_id, request.query)

            if self.sop_recall.is_valid_sop_result(sop_res):
                sop_content = sop_res["data"]["choosed_sop_string"]
                sop_mode = sop_res["data"]["sop_mode"]

                logger.info(f"{request.request_id} SOP召回成功，模式：{sop_mode}, 内容长度：{len(sop_content)}")
                sop_prompt = agent_context.sop_prompt.replace("{{sop}}", sop_content)
                agent_context.sop_prompt = sop_prompt
            else:
                logger.warning(f"{request.request_id} SOP 召回失败或结果无效")
        except Exception as e:
            logger.error(f"{request.request_id} SOP召回处理异常")
            logger.error(traceback.format_exc())


