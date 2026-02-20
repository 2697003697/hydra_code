# Hydra Code

一个开源 CLI 工具，支持动态多模型协作。

## 功能特性

- **动态多模型协作**：多个 AI 模型协同完成复杂任务
- **基于角色的任务分配**：每个模型都有特定角色（Fast, Pro, Sonnet, Opus）
- **工具支持**：文件操作、命令执行、代码库搜索
- **灵活配置**：为任何角色配置任何模型

## 角色说明

| 角色 | 名称 | 职责 |
|------|------|------------------|
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
> 2. 或者直接在项目根目录下运行 `.\hydra.bat`（我已为你创建此快捷方式）。
> 3. 或者继续使用 `python -m hydra_code`。

## 配置

在 `~/.hydra-code` 创建配置文件（首次运行 `hydra --init` 会自动创建）：

```yaml
default_role: fast

max_tokens: 4096
temperature: 0.7
auto_approve: false
verbose: false

roles:
  fast:
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"

  pro:
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"

  sonnet:
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"

  opus:
    api_key: "your-api-key"
    base_url: "https://api.example.com/v1"
    model_name: "model-name"
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

# 多模型协作（无需手动确认）

/complex

```

## 交互命令

| 命令 | 描述 |
|---------|-------------|
| `/help` | 显示帮助信息 |
| `/roles` | 显示角色配置 |
| `/config` | 显示当前配置 |
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

## 配置示例

### 使用不同的 API 提供商

```yaml
roles:
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
    model_name: "gpt-4"

  pro:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "gpt-4"

  sonnet:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "gpt-4"

  opus:
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
    model_name: "gpt-4"

```
