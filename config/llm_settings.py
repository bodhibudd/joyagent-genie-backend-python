from typing import Optional
class LLMSettings:
    def __init__(
            self,
            model: Optional[str] = None,
            max_tokens: int = 0,
            temperature: float = 0.0,
            api_type: Optional[str] = None,
            api_key: Optional[str] = None,
            api_version: Optional[str] = None,
            base_url: Optional[str] = None,
            interface_url: Optional[str] = None,
            function_call_type: Optional[str] = None,
            max_input_tokens: int = 0,
            ext_params: dict = {}
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.api_type = api_type
        self.api_key = api_key
        self.api_version = api_version
        self.base_url = base_url
        self.interface_url = interface_url
        self.function_call_type = function_call_type
        self.max_input_tokens = max_input_tokens
        self.ext_params = ext_params
