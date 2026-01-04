import copy
import json
import re
import time
import uuid
import traceback
from typing import Optional, List

import json_repair
from loguru import logger
from pydantic import BaseModel

from agent.agent.agent_context import AgentContext, ToolCollection
from agent.entity.enums import ToolChoice
from agent.agent.message import Message, ToolCall, Function
from config.llm_settings import LLMSettings
from model.response.agent_response import build_stream_response
from agent.llm.token_counter import TokenCounter
from config.genie_config import genie_config
from util import string_util
import openai
import anthropic


class LLM:
    def __init__(
            self,
            model_name: Optional[str] = None,
            llm_erp: Optional[str] = None
    ):
        self.llm_erp = llm_erp
        llm_settings = LLMSettings(**genie_config.llm_settings_dict[model_name])
        self.model = llm_settings.model
        self.max_tokens = llm_settings.max_tokens
        self.temperature = llm_settings.temperature
        self.api_key = llm_settings.api_key
        self.base_url = llm_settings.base_url
        self.interface_url = llm_settings.interface_url
        self.function_call_type = llm_settings.function_call_type
        self.total_input_tokens = 0
        self.max_input_tokens = llm_settings.max_input_tokens
        self.ext_params = llm_settings.ext_params
        self.token_counter = TokenCounter()

        if openai.__version__.startswith("0."):
            if self.base_url:
                openai.base = self.base_url + self.interface_url
            if self.api_key:
                openai.api_key = self.api_key
            self._chat_complete_create = openai.ChatCompletion.create
        else:
            api_kwargs = {}
            if self.base_url:
                api_kwargs["base_url"] = self.base_url
            if self.api_key:
                api_kwargs["api_key"] = self.api_key

            def _chat_complete_create(*args, **kwargs):
                client = openai.OpenAI(**api_kwargs)
                return client.chat.completions.create(*args, **kwargs)

            self._chat_complete_create = _chat_complete_create

        def _claude_message_create(*args, **kwargs):
            client = anthropic.Anthropic(api_key=self.api_key)
            return client.messages.create(*args, **kwargs)

        self._claude_message_create = _claude_message_create

    def format_messages(self, messages: List[Message], is_claude):
        """格式化消息为大语言模型接口接收的格式"""
        formated_messages = list()
        for message in messages:
            message_dict = {}
            if message.base64_image is not None and len(message.base64_image) != 0:
                multi_modal_list = []
                # 处理base64图像
                image_dict = {"type": "image_url",
                              "image_url": {"url": "data:image/jpeg;base64," + message.base64_image}}
                multi_modal_list.append(image_dict)
                # 处理文本
                text_dict = {"type": "text", "text": message.content}
                multi_modal_list.append(text_dict)
                message_dict["role"] = message.role.value
                message_dict["content"] = multi_modal_list
                formated_messages.append(message_dict)
            elif message.tool_calls is not None and len(message.tool_calls) != 0:
                message_dict["role"] = message.role.value
                if is_claude:
                    claude_tool_calls = list()
                    for tool_call in message.tool_calls:
                        claude_tool_calls.append({
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "input": json.loads(tool_call.function.arguments)
                        })
                    message_dict["role"] = message.role.value
                    message_dict["content"] = claude_tool_calls
                else:
                    message_dict["tool_calls"] = message.tool_calls
            elif message.tool_call_id is not None and len(message.tool_call_id) != 0:
                content = string_util.text_desensitization(message.content, genie_config.sensitive_patterns)
                if is_claude:
                    message_dict["role"] = "user"
                    message_dict["content"] = [
                        {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": content}]
                else:
                    message_dict["role"] = message.role.value
                    message_dict["content"] = content
                    message_dict["tool_call_id"] = message.tool_call_id
            else:
                message_dict["role"] = message.role.value
                message_dict["content"] = message.content
            formated_messages.append(message_dict)

        return formated_messages

    def truncate_message(self, context: AgentContext, messages: list, max_input_tokens):
        if len(messages) == 0 or max_input_tokens < 0:
            return messages

        logger.info(f"{context.request_id} before truncate {messages}")
        t_messages = list()
        remaining_tokens = max_input_tokens
        system_message = messages[0]
        if "system" == system_message.role.value:
            remaining_tokens -= self.token_counter.count_message_tokens(system_message)

        for message in messages[::-1]:
            message_token = self.token_counter.count_message_tokens(message)
            if remaining_tokens >= message_token:
                t_messages.insert(0, message)
                remaining_tokens -= message_token
            else:
                break
        # use assistant 保证完整性
        truncate_messages = []
        for ix, message in enumerate(t_messages):
            if message.role.value != "user":
                continue
            truncate_messages = t_messages[ix:]
            break
        if "system" == system_message.role.value:
            truncate_messages.append(system_message)
        logger.info(f"{context.request_id} after truncate {truncate_messages}")

        return truncate_messages

    def call_openai(self, params: dict, timeout: int):
        """非流式调用"""
        try:
            response = self._chat_complete_create(**params, timeout=timeout)
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise e

    def call_openai_stream(self, params: dict, timeout: int):
        """流式调用,该方法其实最终返回流式调用结果拼接的完整内容"""
        try:
            response = self._chat_complete_create(**params, timeout=timeout)
            full_response = ''
            for chunk in response:
                if hasattr(chunk.choices[0].delta, "content") and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
            return full_response
        except Exception as e:
            raise e

    async def _call_openai_function_call_stream(self, context: AgentContext, params: dict):
        try:
            # 输出流式内容前间隔次数
            intervals = genie_config.message_interval.get("llm", "1,3").split(",")
            first_interval = int(intervals[0])
            send_interval = int(intervals[1])
            index = 1  # 统计是否达到间隔流式输出次数
            is_content = True  # 是否不包含json内容
            response = self._chat_complete_create(**params, timeout=300)
            open_tool_calls_map = dict()
            message_id = str(uuid.uuid4())
            str_builder = list()
            str_all_builder = list()
            #工具问题定位
            calls = []
            for chunk in response:
                if chunk.choices:
                    if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        str_all_builder.append(content)
                        if "struct_parse" == self.function_call_type:
                            if "```json" in "".join(str_all_builder):
                                is_content = False
                        if (not is_content):
                            continue
                        str_builder.append(content)
                        if index == first_interval or index % send_interval == 0:
                            # 输出给前端的数据格式
                            # message_id, stream_message_type, str_builder, is_final
                            data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                         context.stream_message_type, "".join(str_builder), None, False)
                            str_builder.clear()
                            await context.queue.put(data)
                        index += 1

                if hasattr(chunk.choices[0].delta, 'tool_calls') \
                        and chunk.choices[0].delta.tool_calls \
                        and len(chunk.choices[0].delta.tool_calls) != 0:
                    openai_tool_calls = chunk.choices[0].delta.tool_calls
                    calls.append(openai_tool_calls)
                    for tool_call in openai_tool_calls:
                        current_tool_call = open_tool_calls_map.get(tool_call.index, None)
                        if current_tool_call is None:
                            current_tool_call = OpenAIToolCall()
                        if tool_call.id is not None and len(tool_call.id) != 0:
                            current_tool_call.id = tool_call.id
                        if tool_call.type is not None and len(tool_call.type) != 0:
                            current_tool_call.type = tool_call.type
                        if current_tool_call.function is None:
                            current_tool_call.function = OpenAIFunction()
                            current_tool_call.function.arguments = ""
                        if tool_call.function is not None:
                            if tool_call.function.name is not None and len(tool_call.function.name) != 0:
                                current_tool_call.function.name = tool_call.function.name
                            if tool_call.function.arguments is not None and len(tool_call.function.arguments) != 0:
                                current_tool_call.function.arguments += tool_call.function.arguments
                        open_tool_calls_map[tool_call.index] = current_tool_call
            content_all = "".join(str_all_builder)
            if "struct_parse" == self.function_call_type:
                if "```json" in "".join(str_builder):
                    stop_pos = "".join(str_builder).find("```json")
                else:
                    stop_pos = len("".join(str_builder))
                data = build_stream_response(context.request_id, context.agent_type, message_id,
                                             context.stream_message_type, "".join(str_builder)[:stop_pos], None, False)
                await context.queue.put(data)
                if "```json" in content_all:
                    stop_pos = content_all.find("```json")
                else:
                    stop_pos = len(content_all)
                if len(content_all) != 0:
                    data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                 context.stream_message_type, content_all[:stop_pos], None, True)
                    await context.queue.put(data)
            else:
                if len(content_all) != 0:
                    data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                 context.stream_message_type, "".join(str_builder), None, False)
                    await context.queue.put(data)
                    data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                 context.stream_message_type, "".join(str_all_builder), None, True)
                    await context.queue.put(data)

            tool_calls = list()
            if "struct_parse" == self.function_call_type:
                matches = re.findall(r"```json\s*([\s\S]*?)\s*```", content)
                for match in matches:
                    tool_call = self._parse_tool_call(context, match)
                    if tool_call is not None:
                        tool_calls.append(tool_call)
            else:
                for tool_call in open_tool_calls_map.values():
                    tool_calls.append(
                        ToolCall(
                            id=tool_call.id,
                            type=tool_call.type,
                            function=Function(
                                name=tool_call.function.name,
                                arguments=tool_call.function.arguments)
                        )
                    )
            logger.info(f"{context.request_id} call llm stream response {content_all} {tool_calls}")
            logger.info(f"工具结果：{calls}")
            full_response = ToolCallResponse(content=content_all, tool_calls=tool_calls)
            return full_response
        except Exception:
            logger.error(f"{context.request_id} ask tool stream response error or empty")
            raise Exception(f"Unexpected response code:{response}")
        return None

    async def _call_claude_function_call_stream(self, context: AgentContext, params: dict):
        """流式调用，"""
        try:
            intervals = genie_config.message_interval.get("llm", "1,3").split(",")
            first_interval = max(3, intervals[0]) if "struct_parse" == self.function_call_type else int(intervals[0])
            send_interval = int(intervals[1])
            index = 1  # 统计是否达到间隔流式输出次数
            is_content = True  # 是否不包含json内容

            response = self._claude_message_create(**params, timeout=300)
            message_id = str(uuid.uuid4())
            str_list = list()
            str_all_list = list()
            str_tool_list = list()
            open_tool_calls_map = dict()
            tool_id = ""
            for chunk in response:
                if chunk.delta is None:
                    continue

                # content
                if chunk.delta.type == "text_delta":
                    content = chunk.delta.text
                    if not is_content:
                        str_all_list.append(content)
                        continue
                    str_list.append(content)
                    str_all_list.append(content)
                    if "struct_parse" == self.function_call_type:
                        if "```json" in "".join(str_all_list):
                            is_content = False
                            # continue todo,这里是否应该continue
                    if index == first_interval or index % send_interval == 0:
                        # 输出给前端的数据格式
                        # message_id, stream_message_type, str_builder, is_final
                        data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                     context.stream_message_type, "".join(str_list), None, False)
                        str_list.clear()
                        await context.queue.put(data)
                    index += 1

                # tool call
                if chunk.delta.type == "input_json_delta":
                    content = chunk.delta.partial_json
                    str_tool_list.append(content)
                if chunk.message is not None:
                    tool_id = chunk.message.id  # todo claude返回的结果中没有id，这里使用流式输出刚开始时的message id
                else:
                    tool_id = None

            content_all = "".join(str_all_list)

            if "struct_parse" == self.function_call_type:
                if "```json" in "".join(str_list):
                    stop_pos = "".join(str_list).find("```json")
                else:
                    stop_pos = len("".join(str_list))
                data = build_stream_response(context.request_id, context.agent_type, message_id,
                                             context.stream_message_type, "".join(str_list)[:stop_pos], None, False)
                await context.queue.put(data)
                if "```json" in content_all:
                    stop_pos = content_all.find("```json")
                else:
                    stop_pos = len(content_all)
                if len(content_all) != 0:
                    data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                 context.stream_message_type, content_all[:stop_pos], None, True)
                    await context.queue.put(data)
            else:
                if len(content_all) != 0:
                    data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                 context.stream_message_type, "".join(str_list), None, False)
                    await context.queue.put(data)
                    data = build_stream_response(context.request_id, context.agent_type, message_id,
                                                 context.stream_message_type, "".join(str_all_list), None, True)
                    await context.queue.put(data)

            tool_calls = list()
            if "struct_parse" == self.function_call_type:
                matches = re.findall(r"```json\s*([\s\S]*?)\s*```", content)
                for match in matches:
                    tool_call = self._parse_tool_call(context, match)
                    if tool_call is not None:
                        tool_calls.append(tool_call)
            else:
                if len(str_tool_list) != 0:
                    arguments = json_repair.loads("".join(str_tool_list))
                    if "function_name" in arguments:
                        current_tool_call = OpenAIToolCall()
                        current_tool_call.id = tool_id
                        current_tool_call.type = "function"
                        current_tool_call.function.name = arguments["function_name"]
                        current_tool_call.function.arguments = "".join(str_tool_list)
                        open_tool_calls_map[0] = current_tool_call # claude only call one function

                        for tool_call in open_tool_calls_map.values():
                            tool_calls.append(
                                ToolCall(
                                    id=tool_call.id,
                                    type=tool_call.type,
                                    function=Function(
                                        name=tool_call.function.name,
                                        arguments=tool_call.function.arguments)
                                )
                            )

            logger.info(f"{context.request_id} call llm stream response {content_all} tool calls {tool_calls}")
            return ToolCallResponse(content=content_all, tool_calls=tool_calls)
        except Exception as e:
            logger.error(f"{context.request_id} ask tool stream error")
            logger.error(traceback.format_exc())
            raise e
        return None

    def ask(
            self,
            context: AgentContext,
            messages: List[Message],
            system_msgs: List[Message],
            stream: bool,
            temperature: float
    ):
        """向LLM发送请求并获取响应"""
        try:
            formatted_messages = list()
            if system_msgs is not None and len(system_msgs) != 0:
                formatted_sys_msgs = self.format_messages(system_msgs, False)
                formatted_messages.extend(formatted_sys_msgs)
            formatted_messages.extend(self.format_messages(messages, "claud" in self.model))

            # 准备请求参数
            params = dict()
            params["model"] = self.model
            if self.llm_erp is not None and len(self.llm_erp) != 0:
                params["erp"] = self.llm_erp
            params["messages"] = formatted_messages

            params["max_tokens"] = self.max_tokens
            params["temperature"] = temperature
            if len(self.ext_params) != 0:
                params.update(self.ext_params)
            logger.info(f"{context.request_id} call llm ask request: {params}")

            # 处理非流式请求
            if not stream:
                params["stream"] = False
                response = self.call_openai(params, 300)
                logger.info(f"{context.request_id} call llm response {response}")
                choices = response.choices
                if choices is None or len(choices) == 0:
                    raise Exception("Empty or invalid response from LLM")
                return choices[0].message.content
            else:
                # 处理流式请求
                params["stream"] = True
                return self.call_openai_stream(params, 300)
        except Exception as e:
            raise e

    async def ask_tool(
            self,
            context: AgentContext,
            messages: List[Message],
            system_msgs: Message,
            tools: ToolCollection,
            tool_choice: str,
            stream: bool,
            timeout: int,
            temperature
    ):
        """向LLM发送工具请求并获取响应"""

        def tool_choice_valid(choice: str):
            try:
                ToolChoice(choice)
                return True
            except ValueError:
                return False

        def add_function_name_param(params: dict, tool_name: str):
            new_parameters = copy.deepcopy(params)
            new_required = ["function_name"]
            if "required" in new_parameters and len(new_parameters["required"] != 0):
                new_required.extend(new_parameters["required"])
            new_parameters["required"] = new_required

            new_properties = {"function_name": {"description": "默认值为工具名: " + tool_name, "type": "string"}}
            if "properties" in new_parameters and new_parameters["properties"] is not None:
                new_properties.update(new_parameters["properties"])
            new_parameters["properties"] = new_properties
            return new_parameters

        try:
            if not tool_choice_valid(tool_choice):
                raise Exception(f"Invalid tool_choice: {tool_choice}")
            start_time = time.time()
            params = dict()
            formatted_tools = []
            struct_parse_str_list = []
            if "struct_parse" == self.function_call_type:
                struct_parse_str_list.append(genie_config.struct_parse_tool_system_prompt)
                for tool_name in tools.tool_map:
                    func_map = {
                        "name": tool_name,
                        "description": tools.tool_map[tool_name].desc,
                        "parameters": add_function_name_param(tools.tool_map[tool_name].to_params)
                    }
                    struct_parse_str_list.append(f"- `{tool_name}````json {func_map} ```")
                for tool_name in tools.mcp_tool_map:
                    func_map = {
                        "name": tool_name,
                        "description": tools.mcp_tool_map[tool_name].desc,
                        "parameters": add_function_name_param(json.loads(tools.tool_map[tool_name].parameters),
                                                              tool_name)
                    }
                    struct_parse_str_list.append(f"- `{tool_name}````json {func_map} ```")
            else:
                for tool_name in tools.tool_map:
                    func_map = {}
                    func_map["name"] = tool_name
                    func_map["description"] = tools.tool_map[tool_name].desc
                    func_map["parameters"] = tools.tool_map[tool_name].to_params
                    formatted_tools.append({"type": "function", "function": func_map})
                for tool_name in tools.mcp_tool_map:
                    parameters = json.loads(tools.mcp_tool_map[tool_name].parameters)
                    func_map = {}
                    func_map["name"] = tool_name
                    func_map["description"] = tools.mcp_tool_map[tool_name].desc
                    func_map["parameters"] = parameters
                    formatted_tools.append({"type": "function", "function": func_map})
                if "claude" in self.model:
                    formatted_tools = self.gpt2claude_tool(formatted_tools)

            # 格式化消息
            formatted_messages = list()
            if system_msgs is not None:
                if "struct_parse" == self.function_call_type:
                    system_msgs.content = system_msgs.content + "\n" + "\n".join(struct_parse_str_list)
                if "claude" in self.model:
                    params["system"] = system_msgs.content
                else:
                    formatted_messages.extend(self.format_messages([system_msgs], False))

            formatted_messages.extend(self.format_messages(messages, "claude" in self.model))

            params["model"] = self.model
            if self.llm_erp is not None and len(self.llm_erp) != 0:
                params["erp"] = self.llm_erp

            params["messages"] = formatted_messages
            if "struct_parse" != self.function_call_type:
                params["tools"] = formatted_tools
                params["tool_choice"] = tool_choice

            params["max_tokens"] = self.max_tokens
            params["temperature"] = temperature if temperature is not None else self.temperature
            if len(self.ext_params) != 0:
                params.update(self.ext_params)

            logger.info(f"f{context.request_id} call llm request {params}")

            if not stream:
                response = self.call_openai(params, timeout).model_dump()
                logger.info(f"{context.request_id} call llm response {response}")
                choices = response["choices"]
                if choices is None or len(choices) == 0:
                    logger.error(f"{context.request_id} Invalid response: {response}")
                    raise Exception("Invalid or empty response from LLM")
                # 响应内容
                message = choices[0]["message"]
                content = choices[0]["message"]["content"]

                # 提取工具调用
                tool_calls = list()
                if "struct_parse" == self.function_call_type:
                    matches = re.findall(r"```json\s*([\s\S]*?)\s*```", content)
                    for match in matches:
                        tool_call = self._parse_tool_call(context, match)
                        if tool_call is not None:
                            tool_calls.append(tool_call)

                    stop_pos = content.find("```json")
                    if stop_pos > 0:
                        content = content[:stop_pos]
                else:
                    if "tool_calls" in message and message["tool_calls"] is not None:
                        for tool_call in message["tool_calls"]:
                            function_name = tool_call["function"]["name"]
                            arguments = tool_call["function"]["arguments"]
                            tool_calls.append(
                                ToolCall(id=tool_call["id"],
                                         type=tool_call["type"],
                                         function=Function(name=function_name, arguments=arguments)))
                # 提取其他信息
                finish_reason = choices[0]["finish_reason"]
                total_tokens = response["usage"]["total_tokens"]
                end_time = time.time()
                duration = int((end_time - start_time) * 1000)
                return ToolCallResponse(content=content, tool_calls=tool_calls, finish_reason=finish_reason,
                                        total_tokens=total_tokens, duration=duration)
            else:
                # 处理流式请求
                params["stream"] = True
                if "claude" in self.model:
                    return await self._call_claude_function_call_stream(context, params)
                else:
                    return await self._call_openai_function_call_stream(context, params)
        except Exception as e:
            logger.error(f"{context.request_id} Unexpected error in ask_tool: {traceback.format_exc()}")
            raise e

    def _parse_tool_call(self, context, json_content):
        """转换工具格式"""
        try:
            json_obj = json.loads(json_content)
            tool_name = json_obj["function_name"]
            del json_obj["function_name"]
            return ToolCall(id=str(uuid.uuid4()), function={"name": tool_name, "arguments": json_obj})
        except Exception:
            logger.error(f"{context.request_id} parse tool call error {json_content}")
        return None

    def gpt2claude_tool(
            self,
            gpt_tools: list
    ):
        """将openai工具格式转为claude工具格式"""
        new_gpt_tools = copy.deepcopy(gpt_tools)
        claude_tools = list()
        for gpt_tool_wrapper in new_gpt_tools:
            claude_tool_map = {}
            claude_tool_map["name"] = gpt_tool_wrapper["function"]["name"]
            claude_tool_map["description"] = gpt_tool_wrapper["function"]["description"]
            parameters = gpt_tool_wrapper["function"]["parameters"]
            new_required = list()
            new_required.append("function_name")
            if "required" in parameters and len(parameters["required"] != 0):
                new_required.extend(parameters["required"])
            parameters["required"] = new_required

            new_properties = {
                "function_name": {"description": "默认值为工具名: " + gpt_tool_wrapper["function"]["name"], "type": "string"}}
            if "properties" in parameters and parameters["properties"] is not None:
                new_properties.update(parameters["properties"])
            parameters["properties"] = new_properties
            claude_tool_map["input_schema"] = parameters
            claude_tools.append(claude_tool_map)

        return claude_tools


class ToolCallResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None
    total_tokens: Optional[int] = 0
    duration: Optional[int] = 0


class OpenAIFunction(BaseModel):
    name: Optional[str] = None
    arguments: Optional[str] = None


class OpenAIToolCall(BaseModel):
    index: Optional[int] = None
    id: Optional[str] = None
    type: Optional[str] = None
    function: Optional[OpenAIFunction] = None


class OpenAIDelta(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[List[OpenAIToolCall]] = None


class OpenAIChoice(BaseModel):
    index: Optional[int] = None
    delta: Optional[OpenAIDelta] = None
    logprobs: Optional[dict] = None
    finish_reason: Optional[str] = None


class ClaudeDelta(BaseModel):
    text: Optional[str] = None
    partial_json: Optional[str] = None
    type: Optional[str] = None


class ClaudeResponse(BaseModel):
    delta: Optional[ClaudeDelta] = None
