# 模块化语音访谈器设计

## 目标

构建一个可嵌入任意界面的浏览器语音访谈器。它用中文发起并完成多轮市场研究访谈，按访谈模板收集信息，自动追问缺失或矛盾内容，将每轮对话与结构化结论保存到 SQLite，并可导出 JSON。

首版使用任意 OpenAI-compatible Chat Completions API 做语言推理；模型端点、模型名、密钥均由环境变量配置。界面不拥有访谈逻辑，电话、移动端或 LiveKit 版本可复用同一核心。

## 非目标

- 不做外呼电话、登录、多租户、问卷后台、分析仪表盘。
- 不绑定某个 STT/TTS 供应商。
- 不把访谈状态存进浏览器。
- 不在首版创建 LiveKit 版本。

## 方案选择

### 选定：FastAPI 核心 + Pipecat 音频适配层 + 原生 Web 页面

- `FastAPI`：公开小型 HTTP API，处理会话与单轮文本，所有 UI 可调用。
- `InterviewService`：唯一的访谈业务入口。读取模板、调用推理器、校验输出、持久化状态。
- `OpenAICompatibleLLM`：仅依赖 `/v1/chat/completions` 语义；替换端点即可接云端或本地模型。
- `SQLiteInterviewRepository`：标准库 `sqlite3` 保存会话、回合、槽位结论；无 ORM。
- `Pipecat` 适配器：将语音转写文本交给 `InterviewService`，再将返回的访谈提问送回 TTS。STT、TTS、VAD 仅在该层配置。
- `web/`：无框架静态页面。用 REST 调核心；支持文本输入，浏览器支持 `SpeechRecognition` 时启用麦克风转写，使用 `speechSynthesis` 播放访谈者回复。文本回退保证任何界面都能完成访谈。

不用 React、LangGraph、ORM。首版访谈只有一个受控状态机；额外框架不会减少实际复杂度。需要可恢复的长运行工作流、人工审核节点或跨系统工具调用时，再将 `InterviewService` 的决策步骤迁移到 LangGraph。

## 领域模型

`InterviewTemplate` 定义可配置的行业研究问题：

- `title`：研究名称。
- `language`：默认 `zh-CN`，可设 `en-US`。
- `objective`：访谈目标。
- `fields`：每个字段含 `id`、`label`、`purpose`、`required`。

内置通用模板字段：`context`、`current_behavior`、`needs`、`alternatives`、`decision_criteria`、`barriers`。

`InterviewSession` 含 `id`、模板、语言、状态、创建时间、结束时间。

`InterviewTurn` 含序号、受访者文本、访谈者文本、时间。`facts` 是按字段保存的结构化值和证据。

## 回合流程

1. 界面调用 `POST /sessions` 创建会话，服务返回首句开场与第一个问题。
2. 浏览器音频层取得受访者文本，或用户直接输入文本。
3. 界面调用 `POST /sessions/{id}/turns`。
4. `InterviewService` 将历史、模板、当前事实发送给 LLM。
5. LLM 必须只返回 JSON：更新的字段事实、冲突、下一个问题、是否完成、简短面向语音的回复。
6. 服务端验证 JSON、忽略未知字段、写入 SQLite。
7. 返回 `TurnResult`，页面显示并朗读 `interviewer_text`。
8. 所有必填字段均有证据后，服务要求 LLM 生成确认性总结；受访者确认后标记完成并可导出。

LLM 返回无效 JSON、网络失败或缺少密钥时，服务不丢会话。它返回可显示的错误；开发模式下 `ScriptedLLM` 让纯文本流程与测试可运行。

## 接口

```text
POST /sessions
  input:  { template?, language? }
  output: { session_id, interviewer_text, status, missing_fields }

POST /sessions/{session_id}/turns
  input:  { text }
  output: { interviewer_text, status, missing_fields, facts }

GET /sessions/{session_id}
  output: session, turns, facts

GET /sessions/{session_id}/export
  output: JSON export
```

文本 API 是正式集成边界。Web 页面、Pipecat、LiveKit 代理都只能通过此 API 或同一个 `InterviewService` 调用，不复制提示词、槽位逻辑或持久化。

## Pipecat 适配器

Pipecat 管线固定为：

```text
browser transport input -> STT -> user transcript adapter -> InterviewService
  -> interviewer text adapter -> TTS -> browser transport output
```

VAD 与打断由 Pipecat 管理。打断时停止当前 TTS；已经写入 SQLite 的受访者回合保持不变。首版用配置值注入 STT/TTS，不在代码中写供应商密钥。

浏览器样例先使用 Web Speech API，避免配置音频供应商也能运行和检验访谈逻辑。Pipecat 运行器作为可选真实流式语音入口，配置完 STT/TTS 密钥后启动。

## 安全与运行配置

- `.env` 提供 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、数据库路径及可选语音供应商密钥。
- 浏览器不接触 LLM 或语音供应商密钥。
- API 限制空白输入与过长输入；错误响应不泄露密钥或上游原始响应。
- SQLite 文件默认在本机 `data/`，排除版本控制。

## 测试与验收

先写单元测试，再写实现：

1. 首回合生成开场并创建会话。
2. 回答后只更新模板已定义字段。
3. 缺失字段按模板继续追问。
4. 必填字段齐全但未确认时请求总结；确认后完成。
5. 无效 LLM 输出不破坏已保存状态。
6. FastAPI API 测试验证创建、回合、读取、导出。

验收：设置一个兼容 LLM 配置后，打开浏览器页面即可说话或输入文字，完成一次通用市场研究访谈；刷新页面后可从 API 读取完整记录；任意第三方界面可仅靠四个 HTTP 端点接入。

## LiveKit 后续版本

LiveKit 版本仅替换 `web/` 音频接入和 `Pipecat` 适配器，不触碰领域、SQLite、模板与 HTTP 契约。它增加 LiveKit Server、JWT token 端点、Agent Worker 与 React/LiveKit Components 前端。适合需要高可靠 WebRTC、多参与者、电话或生产级回声消除时建立。
