from config.genie_config import GenieConfig
import requests
from http import HTTPStatus
from loguru import logger


class SopRecall:
    def __init__(self, genie_config: GenieConfig):
        self.genie_config = genie_config

    def sop_recall(self, request_id, query):
        sop_recall_url = self.genie_config.auto_bots_knowledge_url + "/v1/tool/sopRecall"
        #sop参数
        sop_req = {"requestId": request_id, "query": query}
        sop_res = requests.post(sop_recall_url, json=sop_req, timeout=3000)
        if sop_res.status_code != HTTPStatus.OK:
            logger.error(f"{request_id} SOP召回服务返回空响应")
            return None

        logger.info(f"{request_id} SOP召回服务响应：{sop_res.json()}")

        return sop_res.json()

    def is_valid_sop_result(self, sop_res):
        if sop_res is None:
            return False
        return True