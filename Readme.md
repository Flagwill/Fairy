# NL2CMD：自然语言到命令行翻译器（基于 GitHub Copilot）

一个终端工具：在任意终端输入 `trans "一句自然语言"`，它将调用大模型把自然语言翻译为可执行的 Shell 命令，并提供修改或一键执行的选择。

使用前需要安装[Github Copilot Cli](https://github.com/features/copilot/cli/)与[GitHub Copilot SDK](https://github.com/github/copilot-sdk/tree/main)
```bash
brew install copilot-cli
pip install github-copilot-sdk
```


## 快速开始

- 本地运行（无需安装）：

```bash
python -m nl2cmd.cli "列出当前目录所有隐藏文件"
# 或
chmod +x scripts/trans && ./scripts/trans "查看最近10条git提交"
```

- 安装为系统命令：

```bash
pip install -e .
trans "查找当前项目中包含TODO的文件"
```

## 使用说明

- 基本用法：

```bash
trans "压缩当前目录为zip并排除node_modules"
```

- 选项：
	- `--shell=/bin/bash`：指定执行Shell（默认`/bin/bash`）
	- `--no-exec` / `--dry-run`：仅输出命令，不执行
	- `-y` / `--yes`：自动确认执行（跳过交互）
	- `-v` / `--verbose`：显示更多调试信息

- 交互：程序会打印推荐命令，并提供 `[e]xecute / [m]odify / [c]ancel / [p]rint` 选项；检测到潜在危险命令（如`sudo`、`rm -rf`）会二次确认。

## Copilot 集成

翻译逻辑使用 GitHub Copilot SDK 的 `CopilotClient`。示例见 [test.py](test.py)。运行前需保证 Copilot SDK 可用并已配置凭据（环境变量或本地配置）。若 SDK 不可用，程序将回退为安全的 `echo` 输出，确保CLI不崩溃。

## 项目结构

- [nl2cmd/cli.py](nl2cmd/cli.py)：命令行入口与交互
- [nl2cmd/translator.py](nl2cmd/translator.py)：翻译自然语言到Shell命令
- [nl2cmd/copilot_client.py](nl2cmd/copilot_client.py)：Copilot客户端封装
- [nl2cmd/prompt.py](nl2cmd/prompt.py)：提示词模板与安全约束
- [nl2cmd/executor.py](nl2cmd/executor.py)：安全执行命令与危险检测
- [scripts/trans](scripts/trans)：未安装时的便捷可执行脚本
- [pyproject.toml](pyproject.toml)：安装与入口配置（`trans`）

## 开发建议

- 提示词可根据场景扩展，例如加入当前目录上下文、已安装工具列表等。
- 可添加执行历史与撤销策略，或加入不同操作系统的适配（当前默认Linux/bash）。
- 如需更丰富的交互界面，可引入TUI库（如`textual`）。

## 许可证

本项目采用 MIT 许可证发布。详情见 [LICENSE](LICENSE)。
