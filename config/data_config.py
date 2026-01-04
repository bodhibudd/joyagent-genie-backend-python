from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
from typing import Optional, List


class DataAgentModelConfig(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    remark: Optional[str] = None
    business_prompt: Optional[str] = None
    ignore_fields: Optional[str] = None
    default_recall_fields: Optional[str] = None
    analyze_suggest_fields: Optional[str] = None
    analyze_forbid_fields: Optional[str] = None
    sync_value_fields: Optional[str] = None
    column_alias_dict: Optional[str] = None


class QdrantConfig(BaseModel):
    enable: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    api_key: Optional[str] = None
    embedding_url: Optional[str] = None


class DbConfig(BaseModel):
    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    schema: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    key: Optional[str] = Field(default="genie-datasource")


class EsConfig(BaseModel):
    enable: Optional[bool] = None
    host: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None


class DataAgentConfig(BaseSettings):
    agent_url: str = Field(default="", validation_alias="autobots.data-agent.agent-url")
    model_list: List[DataAgentModelConfig] = Field(default=[], validation_alias="autobots.data-agent.model-list")
    qdrant_config: QdrantConfig = Field(default=None, validation_alias="autobots.data-agent.qdrant-config")
    db_config: DbConfig = Field(default=None, validation_alias="autobots.data-agent.db-config")
    es_config: EsConfig = Field(default=None, validation_alias="autobots.data-agent.es-config")


data_config = DataAgentConfig()
