# Hydra Code

一个开源 CLI 工具，支持动态多模型协作。

## 功能特性

- **动态多模型协作**：多个 AI 模型协同完成复杂任务
- **模型库管理**：集中管理所有 API 配置，一键切换
- **基于角色的任务分配**：每个模型都有特定角色（Fast, Pro, Sonnet, Opus）
- **实时切换**：运行时动态调整角色对应的模型
- **工具支持**：文件操作、命令执行、代码库搜索
- **灵活配置**：为任何角色配置任何模型
- **安全防护**：路径穿越保护、SSRF 阻断、精确 token 估算

## 角色说明

| 角色 | 名称 | 职责 |
|------|------|------------------|
| chat | Chat | 默认交互角色，负责理解意图并分发任务 |
| fast | Fast | 快速响应，任务分类与分发 |
| pro | Pro | 项目规划与核心代码编写 |
| sonnet | Sonnet | 深度推理与问题解决 |
| opus | Opus | 复杂架构设计与统筹 |

## 安装

推荐使用开发模式安装，这样修改代码后无需重新安装即可生效：

```bash
# 在项目根目录下运行
pip install -e .
```

安装完成后，你可以直接使用 `hydra` 命令启动程序，而不需要输入 `python -m hydra_code`。

> **注意**：如果安装后提示找不到 `hydra` 命令（如 `hydra : 无法将“hydra”项识别为 cmdlet...`），这是因为 Python 的脚本目录没有添加到系统 PATH 环境变量中。
> 
> 解决方法：
> 1. 将报错信息中提示的路径（例如 `...\Python313\Scripts`）添加到系统环境变量 Path 中。
> 2. 或者继续使用 `python -m hydra_code`。

## 配置

在 `~/.hydra-code` 创建配置文件（首次运行 `hydra --init` 会自动创建）。

你可以配置**模型库 (models)**，然后在**角色 (roles)** 中引用它们：

```yaml
default_work_mode: fast
max_tokens: 4096
temperature: 0.7
auto_approve: false
verbose: false

# 1. 定义模型库（存储所有可用的 API 配置）
models:
  deepseek-official:
    provider: deepseek
    api_key: "sk-..."
    base_url: "https://api.deepseek.com"
    model_name: "deepseek-chat"
    description: "DeepSeek 官方接口"

  gpt-4-azure:
    provider: azure
    api_key: "..."
    base_url: "https://my-azure.openai.azure.com"
    model_name: "gpt-4"
    description: "Azure 美东区域"

# 2. 分配角色（引用上面的模型名称，或直接配置）
roles:
  chat: deepseek-official # 默认交互角色
  fast: deepseek-official  # 引用模型库
  pro: gpt-4-azure         # 引用模型库
  sonnet: deepseek-official
  opus:
    # 也可以直接在这里配置（旧方式）
    provider: openai
    api_key: "sk-..."
    model_name: "gpt-4"
```

## 使用方法

```bash
# 初始化配置（创建示例配置文件）
hydra --init

# 启动交互式会话
hydra

# 选择带参模型（如下，此时在调用工具或者执行命令时无需手动确认）
/pro -y

# 显示当前配置
hydra --config
```
# 协作模式

## Leader 模式 (推荐)
由一个 Leader 模型统筹全局，分发任务给其他 Worker 模型。适合复杂任务。实时显示 Round 进度、Worker 状态和活动日志。
```bash
/leader          # 默认使用 Opus 作为 Leader
/leader sonnet   # 指定 Sonnet 作为 Leader
```

## 并行模式
多个模型并行工作，适合无明显依赖的任务。
```bash
/parallel
```

## 自动模式
根据任务特征智能选择执行策略，支持多维度分析：

```bash
/auto
```

### 路由分析维度
Auto 模式会分析以下三个维度：

| 维度 | 取值 | 说明 |
|------|------|------|
| **复杂度** | `simple` / `moderate` / `complex` | 决定使用单模型还是 Leader 协作 |
| **领域** | `coding` / `content` / `general` | 影响 Leader 的策略偏好 |
| **意图** | `new` / `modify` / `qa` | 影响代码修改方式 |

### 执行策略

| 复杂度 | 执行方式 | 模型选择 |
|--------|----------|----------|
| `simple` | 单模型快速响应 | Fast → Sonnet → Opus |
| `moderate` / `complex` | Leader 协作模式 | Opus → Sonnet → Pro |

### 领域感知
Leader 会根据任务领域调整策略：
- **coding**: 严格遵守代码规范，确保代码可运行
- **content**: 侧重于结构清晰、语言优美
- **general**: 直接回答问题，必要时调用工具验证

### 意图感知
Leader 会根据用户意图调整行为：
- **new**: 从头设计实现，确保架构合理
- **modify**: 先理解现有代码，只修改必要部分，保持风格一致
- **qa**: 提供准确详尽的解答


## 交互命令

| 命令 | 描述 |
|---------|-------------|
| `/help` | 显示帮助信息 |
| `/roles` | 显示角色配置 |
| `/config` | 显示当前配置 |
| `/models` | 列出或管理模型配置 |
| `/clear` | 清除对话历史 |
| `/context` | 显示代码库上下文 |
| `/status` | 显示协作状态 |
| `/exit` | 退出 CLI |

## 协作协议

模型之间可以使用特殊标记进行通信：

- `[REQUEST_HELP: role]` - 请求其他角色帮助
- `[SHARE_DISCOVERY]` - 与团队分享发现
- `[DELEGATE: role]` - 委派子任务
- `[HANDOFF: role]` - 将工作移交给其他角色
- `[COMPLETE]` - 标记任务完成

## 远程访问

支持通过浏览器或其他设备远程访问：

```bash
# 启动 Web 服务器
hydra --server --port 8080
```

### 访问方式

| 方式 | 地址 | 说明 |
|------|------|------|
| 本地 | http://localhost:8080 | 本机访问 |
| 局域网 | http://<IP>:8080 | 同一 WiFi 下的手机/电脑 |
| Tailscale | http://<Tailscale IP>:8080 | 远程 P2P 访问 |
| ngrok | http://<ngrok URL> | 公网穿透（需认证） |

### 特性

- **响应式界面**：适配手机、平板、桌面
- **实时通信**：WebSocket 流式响应
- **模式切换**：随时切换 Fast/Auto/Pro/Leader 模式
- **意图解释**：点击"解释"查看路由决策
- **文件管理**：支持上传和下载文件
- **自动重连**：连接断开时自动尝试重连（最多5次）

## 长期记忆

Hydra Code 会随着使用逐渐了解你的偏好：

- **常用模式**：记住你最常用的执行模式
- **沟通习惯**：学习你的常用短语和意图
- **对话历史**：自动摘要关键上下文

记忆数据存储在 `工作目录/.hydra/memory/` 目录，重启后不丢失。

## 安全特性

- **路径穿越防护**：所有文件工具校验路径是否在工作目录内，阻止 `../` 遍历攻击
- **SSRF 防护**：`fetch_url` 工具阻断对 localhost、私有 IP、链路本地地址的访问
- **精确 Token 估算**：使用 tiktoken 精确计算，避免中文内容低估导致上下文溢出
- **并发安全**：消息写入使用线程锁保护，并行模式下不会数据竞争

## 配置示例

### 使用不同的 API 提供商

```yaml
roles:
  chat:
    api_key: "deepseek-key"
    base_url: "https://api.deepseek.com/v1"
    model_name: "deepseek-chat"

  fast:
    api_key: "stepfun-key"
    base_url: "https://api.stepfun.com/v1"
    model_name: "step-3.5-flash"

  pro:
    api_key: "qwen-key"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name: "qwen-plus"

  sonnet:
    api_key: "deepseek-key"
    base_url: "https://api.deepseek.com/v1"
    model_name: "deepseek-chat"

  opus:
    api_key: "glm-key"
    base_url: "https://open.bigmodel.cn/api/paas/v4"
    model_name: "glm-4-flash"
```

### 所有角色使用同一个模型

```yaml
roles:
  fast:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "example"

  pro:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "example"

  sonnet:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "example"

  opus:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "example"

```
