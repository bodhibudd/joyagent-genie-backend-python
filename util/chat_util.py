import re

from agent.entity.auto_bots_result import AutoBotsResult
from agent.entity.enums import AutoBotsResultStatus
from model.protocal import GptQueryReq


class ChatUtils:
    SOURCE_MOBILE = "mobile"
    SOURCE_PC = "pc"
    NO_ANSWER = "哎呀，超出我的知识领域了，换个问题试试吧"

    @classmethod
    def has_chinese(cls, s: str) -> bool:
        """是否包含至少一个中文字符"""
        if not isinstance(s, str):
            return True
        CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fa5]')
        return bool(CHINESE_PATTERN.search(s))

    @classmethod
    def get_request_id(cls, erp, trace_id, req_id):
        erp = erp.lower() if erp is not None else erp
        if cls.has_chinese(erp):
            return trace_id + ":" + req_id
        else:
            return erp + trace_id + ":" + req_id

    @classmethod
    def to_auto_bots_result(cls, request, status):
        result = AutoBotsResult(
            trace_id=request.request_id,
            req_id=request.request_id,
            status=status
        )
        if AutoBotsResultStatus.NO.value == status:
            result.finished = True
            result.response = ChatUtils.NO_ANSWER
            result.response_all = ChatUtils.NO_ANSWER

        return result




