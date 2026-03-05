# Tools

## check_models.py

向指定的 OpenAI 模型发送一条消息并打印各模型的回答，用于快速对比不同模型的响应。

### 依赖

```bash
pip3 install openai
```

### 配置

在环境变量中设置 OpenAI API Key：

```bash
export OPENAI_API_KEY='your-api-key'
```

### 使用

```bash
python3 check_models.py
```

### 修改测试模型或问题

编辑 `check_models.py` 中的以下两行：

```python
models = ["gpt-3.5-turbo", "gpt-4o-mini", "gpt-5-nano"]
question = "what is 1 plus 1"
```
