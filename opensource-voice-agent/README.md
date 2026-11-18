# 开源语音访谈器

本项目把结构化访谈流程落在本地：浏览器负责访谈界面、文字输入和可选的浏览器语音识别；FastAPI 提供 HTTP API；`InterviewService` 负责模板、追问、事实提取和状态；SQLite 持久化会话；LLM 通过 OpenAI-compatible HTTP API 调用。

边界很明确：当前项目不是完整的实时语音运行时。浏览器语音识别只是输入辅助，Pipecat 适配器只把一段已完成的 transcript 交给 `InterviewService.reply()`，再返回要朗读的文本。STT、TTS、VAD 和实时 transport 由部署者选择和配置。

## 快速开始

要求：Python 3.12+、[uv](https://docs.astral.sh/uv/)。

```bash
uv sync
cp .env.example .env
```

手动编辑 `.env`，至少配置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。不要把 API key 放进浏览器代码、前端环境变量或公开仓库。

应用读取进程环境变量。Python 不会自动加载 `.env`。使用 Uvicorn 的 `--env-file` 启动：

```bash
uv run uvicorn voice_interviewer.api:app --env-file .env --reload
```

这里的 `voice_interviewer.api:app` 是模块级 ASGI app 对象，不要加 `--factory`。

打开 <http://127.0.0.1:8000>。

也可以在 shell 中导出 `.env`，再运行不带 `--env-file` 的命令：

```bash
set -a
source .env
set +a
uv run uvicorn voice_interviewer.api:app --reload
```

不要只执行 `uv run uvicorn ...` 后期待应用自动读取 `.env`。

## 浏览器语音

输入框始终可用，是文字回退路径。麦克风按钮仅在浏览器提供 `SpeechRecognition` 或 `webkitSpeechRecognition` 时显示；该 Web Speech API 的实现、权限和联网要求因浏览器和平台而异。语音识别结果会先填入文字框，确认后才提交；项目不假设所有浏览器都支持它。

## HTTP API

```bash
# 创建中文访谈
curl -X POST http://127.0.0.1:8000/sessions \
  -H 'Content-Type: application/json' \
  -d '{"language":"zh-CN"}'

# 提交回答。把 SESSION_ID 替换为上一步返回的值
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/turns \
  -H 'Content-Type: application/json' \
  -d '{"text":"我主要为家人购买咖啡"}'

# 读取当前会话
curl http://127.0.0.1:8000/sessions/SESSION_ID

# 导出会话、所有 transcript turn 和已提取 facts
curl http://127.0.0.1:8000/sessions/SESSION_ID/export
```

默认 SQLite 文件为 `data/interviews.sqlite3`，可用 `DATABASE_PATH` 改变。`GET /sessions/{session_id}/export` 返回会话、turns 和 facts；数据在服务重启后仍保留。

## LLM 配置

变量：

- `LLM_BASE_URL`：OpenAI-compatible API 根地址，形如 `https://llm.example.com/v1`，必须以 `/v1` 这类 API 版本路径结尾，不要填 `/chat/completions`。
- `LLM_API_KEY`：服务端使用的密钥。
- `LLM_MODEL`：模型 ID。
- `DATABASE_PATH`：SQLite 文件路径。

示例：

```dotenv
LLM_BASE_URL=https://llm.example.com/v1
LLM_API_KEY=replace-with-a-server-side-key
LLM_MODEL=replace-with-a-model-id
DATABASE_PATH=data/interviews.sqlite3
```

源码不绑定任何 provider-specific key；只读取上述通用变量。

## 开发检查

```bash
uv run pytest -q
uv run python -m compileall -q src
uv build
```

## 可选 Pipecat 适配器

正常安装不包含 Pipecat。需要时安装命名 extra：

```bash
uv sync --extra voice
```

适配器用法：

```python
from voice_interviewer.pipecat_adapter import handle_transcript

spoken_text = handle_transcript(service, session_id, transcript)
```

`handle_transcript()` 只调用 `service.reply(session_id, transcript)`，只返回 `TurnResult.interviewer_text`。它不是完整的 Pipecat streaming runtime。

诚实的 pipeline 伪代码如下，具体类名和参数取决于所选 provider：

```python
transport = configure_transport()  # WebRTC/WebSocket/etc.; credentials and room config
vad = configure_vad()              # turn/silence detection
stt = configure_stt()              # audio -> completed transcript
tts = configure_tts()              # text -> audio; voice and credentials

def on_transcript(session_id, transcript):
    text = handle_transcript(service, session_id, transcript)
    return tts.speak(text)

pipeline = transport.input() | vad | stt | on_transcript | tts | transport.output()
run(pipeline)
```

生产配置仍需补齐：实时 transport、STT provider、TTS provider、VAD/turn detection、会话与身份映射、provider credentials、错误和中断处理。不要把这些假装成当前适配器已经提供的能力。LiveKit 集成特意延期到后续独立版本。
