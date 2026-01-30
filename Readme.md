# 这是一个测试项目
## 作者还没还有想好该怎么介绍它awa
# NL→CMD (GitHub Copilot)

一个基于 GitHub Copilot 的自然语言到命令行翻译器：你输入意图，模型生成命令并在系统终端执行，随后把终端输出纳入后续上下文。

## 结构

- os/: 终端交互与安全过滤
	- terminal.py: 执行命令、收集输出、提供上下文聚合
	- safety.py: 危险命令的基础拦截
- prompts/: 提示模板
	- nl2cmd_system.md: 系统提示（NL→Shell 的规则与格式）
- main.py: 主程序，集成 Copilot SDK 与终端接口
- test.py: Copilot SDK 的最小示例

## 运行

确保已配置可用的 Copilot SDK 与相应凭据。

```
python3 main.py
```

随后按提示输入自然语言指令；按回车触发翻译与执行；空行退出。

## 注意事项

- 模型只返回单行命令；若多步则使用 `&&`。
- 程序包含基础危险命令拦截（如 `rm -rf /`、磁盘格式化等），但无法完全保证安全，请谨慎确认写操作。
- 打开网页请使用环境变量 `$BROWSER`，例如：`$BROWSER "https://example.com"`。

## 开发

- 终端上下文通过 `TerminalRunner.get_recent_output()` 注入到提示模板，有助于提高命令的正确性。
- 如需更丰富的快捷键或 UI，可在 VS Code 扩展或前端层实现；当前 CLI 版本以回车作为触发动作。