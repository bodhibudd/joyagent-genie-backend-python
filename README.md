### 项目介绍

该项目是我对京东JoyAgent-Genie中genie-backend进行的python版改造，目前除智能问数部分正在改造外，其他功能已改造完成。在对该项目改造的过程中，受益良多。京东的joyagent确实是一个很优秀的项目。

### 配置说明

在当前项目配置基础上必须要配置的参数如下：

```
autobots.autoagent.planner.model_name 该参数指定规划时要使用的模型 例如qwen-max
autobots.autoagent.executor.model_name 该参数指定执行步骤时使用的模型
autobots.autoagent.react.model_name 该参数执行react模式下使用的模型
autobots.autoagent.code_interpreter_url 调用工具端文件工具，报告工具，代码工具的url
autobots.autoagent.deep_search_url 搜索工具url
autobots.autoagent.knowledge_url 目前只有在获取sop时用到
autobots.autoagent.multimodalagent_url 多模态工具url
以上url地址一样，都是genie-tool的url地址
autobots.autoagent.mcp_client_url mcp客户端url
autobots.autoagent.mcp_server_url mcp server url
llm.settings llm配置项
其他参数有默认值，可修改
```

### 演示

![image-20260104174525242](C:\Users\Administrator\AppData\Roaming\Typora\typora-user-images\image-20260104174525242.png)

深度研究：

![image-20260104174801783](C:\Users\Administrator\AppData\Roaming\Typora\typora-user-images\image-20260104174801783.png)

表格模式：

![image-20260104184803577](C:\Users\Administrator\AppData\Roaming\Typora\typora-user-images\image-20260104184803577.png)

### 项目启动

python server.py