import json
from typing import List
from agent.entity.file import File


def format_file_info(files: List[File], filter_internal_file):
    """格式化文件信息"""
    file_str_list = []
    for file in files:
        file = File.model_validate_json(json.dumps(file, ensure_ascii=False))
        if filter_internal_file and file.is_internal_file:
            continue
        oss_url = file.origin_oss_url if file.origin_oss_url is not None and len(file.origin_oss_url) != 0 else file.oss_url
        file_str_list.append(f"fileName:{file.file_name} fileDesc:{file.description} fileUrl:{oss_url}")
    return "\n".join(file_str_list)