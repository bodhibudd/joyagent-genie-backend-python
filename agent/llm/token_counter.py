import math

from agent.agent.message import Message


class TokenCounter:
    # Token常量
    BASE_MESSAGE_TOKENS = 4
    FORMAT_TOKENS = 2
    LOW_DETAIL_IMAGE_TOKENS = 85
    HIGH_DETAIL_TILE_TOKENS = 170

    # 图像处理常量
    MAX_SIZE = 2048
    HIGH_DETAIL_TARGET_SHORT_SIDE = 768
    TILE_SIZE = 512

    def count_text(self, text: str):
        """计算文本中的token数量"""
        return 0 if text is None else len(text)

    def count_content(self, content: str | list):
        if content is None:
            return 0
        if isinstance(content, str):
            return len(self.count_text(content))
        if isinstance(content, list):
            token_count = 0
            for c in content:
                if isinstance(c, str):
                    token_count += len(c)
                elif isinstance(c, dict):
                    if c["type"] == "text":
                        token_count += self.count_text(c["text"])
                    elif c["type"] == "image_url":
                        token_count += self.count_image(c["image_url"])
            return token_count

        return 0

    def count_image(self, image_item: dict):
        """计算图像的token数量"""
        detail = image_item.get("detail", "medium")
        # 低细节级别固定返回85个token
        if "low" == detail:
            return TokenCounter.LOW_DETAIL_IMAGE_TOKENS
        # 高细节级别根据尺寸计算
        if "high" == detail or "medium" == detail:
            if "dimensions" in image_item:
                dimensions = image_item["dimensions"]
                return self.calculate_high_detail_tokens(dimensions[0], dimensions[1])

        if "high" == detail:
            return self.calculate_high_detail_tokens(1024, 1024)
        elif "medium" == detail:
            return 1024
        else:
            return 1024

    def calculate_high_detail_tokens(self, width, height):
        """计算高细节图像的token数量"""
        # 步骤1：缩放到MAX_SIZE x MAX_SIZE正方形内
        if width > TokenCounter.MAX_SIZE or height > TokenCounter.MAX_SIZE:
            scale = TokenCounter.MAX_SIZE * 1.0 / max(width, height)
            width = int(width * scale)
            height = int(height * scale)
        # 步骤2: 缩放最短边到HIGH_DETAIL_TARGET_SHORT_SIDE
        scale = TokenCounter.HIGH_DETAIL_TARGET_SHORT_SIDE * 1.0 / min(width, height)
        scale_width = int(width * scale)
        scale_height = int(height * scale)
        # 步骤3
        tiles_x = int(math.ceil(scale_width * 1.0 / TokenCounter.TILE_SIZE))
        tiles_y = int(math.ceil(scale_height * 1.0 / TokenCounter.TILE_SIZE))
        total_tiles = tiles_x * tiles_y

        # 步骤4: 计算最终token数量
        return total_tiles * TokenCounter.HIGH_DETAIL_TILE_TOKENS + TokenCounter.LOW_DETAIL_IMAGE_TOKENS

    def count_message_tokens(self, message: Message):
        tokens = TokenCounter.BASE_MESSAGE_TOKENS
        #添加角色 token
        tokens += self.count_text(message.role.value)
        #//添加内容
        if message.content is not None:
            tokens += self.count_content(message.content)


