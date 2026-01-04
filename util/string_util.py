import re


def text_desensitization(content: str, sensive_pattern: dict):
    # todo 暂未处理
    # 邮箱地址脱敏
    # email_matchs = re.findall("[a-zA-Z0-9\._%\+\-]+@[a-zA-Z0-9\.-]+\.[a-zA-Z]{2,}", content)
    # for email_match in email_matchs:
    #     mask_idx = email_match.find("@")
    #     content = re.sub(email_match, )
    # for pattern in sensive_pattern:
    #     pass
    return content

def remove_special_chars(chars):
    if chars is None or len(chars) == 0:
        return ""
    #定义需要过滤的特殊字符集合
    special_chars = " \"&$@=;+?\\{^}%~[]<>#|'";
    special_chars_set = set()
    for c in special_chars:
        special_chars_set.add(c)

    results = list()
    for c in chars:
        if c not in special_chars_set:
            results.append(c)
    return "".join(results);

