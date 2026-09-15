# WeChatAlive

> 让你的 Windows 微信账号“活”起来，变成群里会聊天的 AI 群友。

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows)](https://github.com/Aiden-723/WeChatAlive)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-green.svg)](LICENSE)
[![Windows smoke test](https://github.com/Aiden-723/WeChatAlive/actions/workflows/windows-smoke.yml/badge.svg)](https://github.com/Aiden-723/WeChatAlive/actions/workflows/windows-smoke.yml)
[![GitHub stars](https://img.shields.io/github/stars/Aiden-723/WeChatAlive?style=social)](https://github.com/Aiden-723/WeChatAlive/stargazers)

群成员真正 `@` 机器人账号后，WeChatAlive 会调用你自己选择的 OpenAI 兼容模型，并把回答发回原群。接口地址、模型 ID、API Key 和角色人格均由使用者自行配置，项目不绑定任何模型厂商。

如果这个项目让你的微信群更有意思，欢迎点一个 **Star** ⭐

## 已实现

- 支持微信 4.1.x Windows 客户端
- 自动发现当前及后来加入的微信群
- 仅原生 `@机器人` 时调用模型，普通群消息不会发送给模型
- 支持任意 OpenAI 兼容接口，可自由填写模型 ID
- 支持角色提示词、温度、记忆轮数和回复长度设置
- 深色可视化管理界面，可启动、停止、重启并查看状态
- 每位群友分别保留短期上下文
- 消息指纹、发送指纹和单实例保护，降低重复回复风险
- 微信最小化到任务栏时可继续运行；锁屏或完全退出微信时不能发送

## 环境要求

- Windows 10/11
- 64 位 Python 3.9+（建议从 python.org 安装，并勾选 `Add Python to PATH`）
- Windows 微信 4.1.x，已登录
- 任意 OpenAI 兼容 API 的接口地址、API Key 和模型 ID

本项目使用个人微信客户端的本地数据库与界面自动化能力，不是微信官方机器人接口。请低频、合规使用；客户端更新可能导致兼容性变化，账号风险需自行评估。

## 安装

1. 下载或克隆本仓库。
2. 双击 `首次安装.bat`，等待依赖安装完成。
3. 打开自动生成的 `填写API密钥.txt`，把等号后面的占位文字换成你的 API Key。
4. 双击 `启动管理界面.bat`。
5. 在“连接信息”填写 OpenAI 兼容接口地址，在“模型设置”填写准确的模型 ID。
6. 按需调整身份设定，然后点击“保存并重启”。

模型和接口默认留空，不会替使用者选择厂商。例如，接口地址通常以 `/v1` 结尾，模型 ID 必须与服务商控制台显示的名称完全一致。

## 隐私设计

以下内容已被 `.gitignore` 排除，不应提交到 GitHub：

- `填写API密钥.txt`
- `bot_config.json`
- `.bot-data/`、`.probe-data/`、`.diagnose-data/`
- 微信数据库缓存、消息水位、聊天指纹和运行日志

发布前仍建议执行 `git status`，确认没有意外加入个人文件。

## 回复规则

- 只处理文本消息。
- 只有微信生成的原生 `@昵称` 标记才会触发；手打普通的 `@名字` 不触发。
- 当前短期记忆在进程内保存，重启机器人后清空。
- 为防刷屏，同一条消息只处理一次，同一群相同答案在短时间内不会重复发送。

## 项目来源

底层微信读取和界面自动化能力基于开源项目 [fanyuantaier/wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica)，并保留其 Apache-2.0 许可证。本仓库在其基础上增加了通用模型接入、群聊机器人、动态群发现、去重保护和可视化管理界面。

## 免责声明

本项目仅用于个人学习和低风险自动化实验。它不是腾讯或阿里云官方产品，也不保证兼容所有微信版本。不要用于群发、骚扰、欺诈、绕过平台限制或处理敏感信息。
