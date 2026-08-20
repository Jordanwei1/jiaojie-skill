<div align="center">

# 交接.skill

<p align="center">
  <img src="assets/hero.gif" alt="Jiaojie Hero Animation" />
  <br/>
  <sub>AI 换了，工作没断。</sub>
</p>

> *「换窗口，不失忆；换模型，不重来。」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-Standard-green)](https://agentskills.io)
[![skills.sh](https://img.shields.io/badge/skills.sh-Compatible-blue)](https://skills.sh)
[![Multi-Runtime](https://img.shields.io/badge/Runtime-Claude%20Code%20·%20Codex%20·%20Cursor%20·%20OpenClaw%20·%20Gemini%20CLI-blueviolet)](#安装)

<br>

**Jiaojie 把目标、决策、废案、产物和下一步交给另一个 AI，让它从你真正停下的地方继续。**

<sub>基于开放的 [Agent Skills 协议](https://agentskills.io)，面向 Claude Code、Codex、Cursor、OpenClaw、Gemini CLI、OpenCode 等兼容 runtime；实际验证范围以公开兼容矩阵为准。</sub>

<br>

[handoff skill](https://github.com/mattpocock/skills/tree/main/skills/productivity/handoff) 证明了把任务摘要交给下一个 Agent 是可行的。<br>
那为什么只交摘要？把意图演化、废弃方案、负知识、产物和真正的下一步一起交过去。<br>
只需说一句「交接一下」，Jiaojie 自动完成导出、接收确认和连续性验证。

[看效果](#效果示例) · [安装](#安装) · [它交接了什么](#jiaojie-交接了什么) · [工作原理](#工作原理)

<br>

**其他语言 / Other Languages:**

[English](README_EN.md) · [Français](README_FR.md) · [日本語](README_JA.md) · [한국어](README_KO.md) · [Español](README_ES.md)

<br>

[![GitHub Stars](https://img.shields.io/github/stars/Jordanwei1/jiaojie-skill?style=social)](https://github.com/Jordanwei1/jiaojie-skill/stargazers)

</div>

---

## 效果示例

### 中文交出，法语接住

一段多轮编程对话已经走到这里：

```text
用户      ❯ 支付 webhook 偶尔会被重复处理。
            不能更换数据库，也不能更换支付平台。

AI A      ❯ request_id 方案验证失败：同一个事件重投时，
            request_id 会变化，不能作为幂等键。

用户      ❯ 不要使用 Redis 锁，我不接受新的运行依赖。
            改用支付平台的 event_id 和数据库唯一约束。

用户      ❯ 下一步并行修改 handler.py 和补 replay 测试，
            最后再更新法语运行手册。交接一下。
            接收方在另一台电脑上，把必需文件一起带走。

AI A      ❯ 已选择 handoff.zip：下一步依赖 handler.py
            和 failure-log.txt，接收方无法访问当前工作区。
```

用户把交接包交给一个没有原会话的 AI B：

```text
用户      ❯ 接收这个交接包。用法语回复，但不要继续执行。

AI B      ❯ Réception réussie. Je n’ai pas poursuivi,
            conformément à votre demande.

            Objectif actuel : empêcher le retraitement des webhooks
            avec event_id et une contrainte unique.

            Point d’arrêt : request_id a échoué techniquement ;
            Redis a été refusé par l’utilisateur. Ne réactiver
            aucune de ces deux options.

            Prochaine étape : modifier handler.py et ajouter les
            tests de rejeu en parallèle, puis mettre à jour le
            runbook en français.

            À revérifier : la stabilité actuelle de event_id chez
            le fournisseur et l’autorisation avant toute modification.
```

换了会话、模型、设备和语言之后，接收 AI 仍然：

- 没有重新询问已经回答的问题；
- 没有复活技术失败的 `request_id` 方案；
- 没有复活被用户否决的 Redis 方案；
- 找到了相同的并行下一步，并按要求停在执行之前。

这就是 Jiaojie 要保护的工作连续性。跨模型、跨语言和 Runtime 的实际表现，以公开评测结果为准。

---

## 安装

Jiaojie 基于开放的 [Agent Skills](https://agentskills.io) 标准。安装器能把 Skill 放进多个 Agent 的发现目录；这只表示“能够安装”，实际语义兼容性以项目公开的测试证据为准。

### 方式一：直接告诉你的 AI

把下面这句话发给支持安装 Skill 的 AI：

```text
帮我安装这个 Skill：
https://github.com/Jordanwei1/jiaojie-skill
```

### 方式二：通用安装器

使用 [vercel-labs/skills](https://github.com/vercel-labs/skills) 安装：

```bash
npx skills add Jordanwei1/jiaojie-skill
```

默认安装到当前项目。希望所有项目都能使用时：

```bash
npx skills add Jordanwei1/jiaojie-skill --global
```

也可以先试用，不写入本地 Skill 目录：

```bash
npx skills use Jordanwei1/jiaojie-skill
```

### 方式三：GitHub CLI

Jiaojie 的 `SKILL.md` 位于仓库根目录，因此使用精确路径安装：

```bash
gh skill install Jordanwei1/jiaojie-skill SKILL.md --agent codex --scope user
```

把 `codex` 换成 `claude-code`、`cursor`、`gemini-cli`、`openclaw` 或其他受支持的 Agent 标识即可。需要可复现安装时，在正式版本发布后使用 `--pin <tag-or-commit>`。

### Codex

在 Codex 中也可以直接调用内置安装器：

```text
请使用 $skill-installer 从下面的仓库安装 Jiaojie：
https://github.com/Jordanwei1/jiaojie-skill
```

Codex 通常会自动发现新安装的 Skill；如果没有出现，重启 Codex 后再检查。OpenAI 官方说明见 [Build skills](https://learn.chatgpt.com/docs/build-skills)。

### 不支持自动安装的 Runtime

直接向 AI 提供 [`SKILL.md`](SKILL.md)。Jiaojie 的最低接收能力只要求能够读取 Markdown；脚本、文件系统和压缩包支持属于增强能力。

---

### 使用

生成交接：

```text
交接一下。
```

只接收、不执行：

```text
接收这个交接包，先给我接收回执，不要继续执行。
```

确认后继续：

```text
继续执行交接包中的建议下一步。
```

Jiaojie 默认选择最小充分产物：普通任务使用 `handoff.md`；必要文件必须随包移动时使用 `handoff.zip`；只有正式审计、跨组织交付或证据要求才使用 `handoff-audit.zip`。

---

## Jiaojie 交接了什么

普通摘要回答“聊过什么”，Jiaojie 要回答“现在到底做到哪里，为什么，以及下一步如何不走回头路”。

| 层 | 保存内容 | 解决的问题 |
| --- | --- | --- |
| HOT | 当前目标、精确停止点、一个推荐下一步、完成标准 | 接收 AI 从正确位置开始 |
| WARM | 有效决定、意图演化、约束、已回答问题、废案与失败原因 | 不重问、不反悔、不复活旧方案 |
| COLD | 必要证据、原始材料、附件、Manifest、哈希与缺失声明 | 需要时可定位、可移动、可验证 |

它还明确区分四件容易被混淆的事：

- **技术失败**：方案经过尝试但不可行；
- **用户否决**：用户不接受，即使技术上可行也不能擅自恢复；
- **历史决定**：解释过去，但不自动授予现在执行、发布、付款或删除的权限；
- **外部事实**：可能已经过期，接收后必须按需要重新验证。

Jiaojie 的“无损”只指声明范围内、用户可见知识边界中的工作连续性。它不保存模型参数、神经状态、隐藏推理或任何平台未提供的内容。

---

## 工作原理

```mermaid
flowchart LR
    A["当前会话<br/>目标 · 决策 · 废案 · 产物"] --> B["EXPORT<br/>选择最小充分格式"]
    B --> C["handoff.md"]
    B --> D["handoff.zip"]
    B --> E["handoff-audit.zip"]
    C --> F["RECEIVE<br/>先确认语义与缺口"]
    D --> F
    E --> G["VERIFY_STRUCTURE<br/>验证结构与字节"]
    G --> F
    F --> H["新会话 / 新模型 / 新设备 / 新语言"]
    H --> I["经用户授权后继续"]
```

Jiaojie 有四种对称模式：

1. `EXPORT`：从当前可见上下文生成交接；
2. `RECEIVE`：把交接恢复成简洁回执，只有用户要求时才继续；
3. `VERIFY_STRUCTURE`：确定性检查审计包的 Schema、路径、Manifest、哈希与图结构；
4. `CONVERT_LEGACY`：把传统 `HANDOFF.md`、OCH Snapshot 或 LTM Packet 保守转换为 `PARTIAL` 交接。

旧格式转换不会伪装成无损：转换报告会列出缺少的原始层、意图演化或附件，并保持 `PARTIAL`。

### 三种输出，不把复杂度强加给所有人

| 输出 | 什么时候用 | 默认内容 |
| --- | --- | --- |
| `handoff.md` | 文字和稳定路径足够 | 一份人类可读 Markdown |
| `handoff.zip` | 下一步必需文件无法由接收方访问 | `HANDOFF.md` + 最小附件集 |
| `handoff-audit.zip` | 正式审计、跨组织交付、可移植证据 | HOT/WARM/COLD + Manifest + 验证材料 |

切换模型、语言或设备本身不会强制升级成 ZIP。格式由“下一步是否依赖不可访问文件”决定。

---

## 多语言不是翻译功能，而是语义保护

Jiaojie 使用 UTF-8 和 BCP 47 语言标签。原文保持权威，译文属于派生视图；代码、路径、标识符、哈希、数字、日期和单位作为受保护片段，不被随意翻译。

跨语言接收时，接收 AI 可以用用户指定的语言回复，但必须保留：

- 决策状态和因果关系；
- `用户否决` 与 `技术失败` 的区别；
- `ACTIVE`、`SUPERSEDED`、`DENIED` 等控制状态；
- 原始证据定位和完整性声明；
- 任何需要重新验证的外部状态。

项目附带 Unicode、双向文本、语言标签和保护片段测试向量。结构测试通过不等于某个模型的跨语言语义测试已经通过；两类成绩分开公布。

---

## 安全与诚实边界

交接包是不可信输入，不是新的系统指令。接收方必须把包内文本、附件和旧授权都当作数据处理。

- 不打包密码、Token、私钥、`.env` 值或无权转移的个人数据；
- 拒绝路径穿越、符号链接逃逸、嵌套归档、ZIP bomb、危险 Unicode 控制符和活动内容；
- 包内 Prompt Injection 不能覆盖当前用户、系统或 Runtime 的指令；
- 哈希证明字节一致，不证明内容真实、安全、获准或仍然有效；
- `FULL` 只是 Producer 对可见边界的声明，接收与验证结果独立记录；
- `PARTIAL`、`UNKNOWN` 和缺失范围必须明确展示，禁止自动补齐后假装完整；
- 历史会话永远不会自动转移当前外部副作用权限。

详细边界见 [`references/security-boundary.md`](references/security-boundary.md) 与 [`references/threat-model.md`](references/threat-model.md)。发现安全问题请按 [`SECURITY.md`](SECURITY.md) 私下报告。

---

## Continuity Fidelity Scorecard

Jiaojie 不只检查“文件能不能打开”，还检查“换了 AI 后工作有没有变”。公开评测分六个维度：

| 维度 | 权重 | 关注点 |
| --- | ---: | --- |
| 意图保真 | 20 | 当前真实目标及其变化是否恢复 |
| 决策演化 | 20 | 有效、覆盖、否决和失败路径是否区分 |
| 负知识 | 20 | 禁止事项、废案与失败原因是否保留 |
| 事实与产物 | 15 | 关键事实、证据、文件与缺失是否可定位 |
| 下一步等价 | 15 | 接收 AI 是否找到相同或等价的下一动作 |
| 完整性诚实 | 10 | 是否拒绝把未知和 partial 伪装成完整 |

总分不能覆盖硬失败。以下任一项失败，当前运行就不能称为连续性通过：

- 重问已经回答的关键问题；
- 复活被否决、废弃或已证明失败的路径；
- 改变关键约束、当前意图或授权边界；
- 混淆用户否决和技术失败；
- 因缺失旧会话而改变下一步，却没有声明缺口；
- 把 `PARTIAL` 说成 `FULL`；
- 翻译时破坏受保护标识符或因果关系。

评测方法、提示与结果格式位于 [`evals/`](evals/)。项目测试、模型测试与第三方复现分别标记，失败结果与成功结果使用同一准入规则。

---

## 能力与证据状态

符号含义：✅ 有仓库内可复现证据；◐ 已实现或有候选方案，但仍依赖模型、Runtime 或第三方验证；— 未提供。

| 能力 | 当前状态 | 证据入口 |
| --- | :---: | --- |
| 七个通用领域模板 | ✅ | [`references/domain-coding.md`](references/domain-coding.md) 等领域参考 |
| 意图与决策演化 | ✅ | 协议、Schema 与离线用例 |
| 跨设备自包含附件 | ✅ | `handoff.zip` 回环测试 |
| HOT / WARM / COLD 原始层 | ✅ | LCH 审计格式与测试向量 |
| `FULL / PARTIAL / UNKNOWN` 声明 | ✅ | 模板、Schema 与验证器 |
| 接收语义确认 | ✅ | RECEIVE 流程与回环测试 |
| 确定性安全与结构测试 | ✅ | [28 项公开记录](evals/results/project-deterministic-2026-08-20/) 与 CI |
| 跨模型、跨语言语义连续性 | ◐ | 方法和运行器已提供；只按公开运行单元申报 |
| 八个 Runtime 的真实安装与行为 | ◐ | 兼容记录模板已提供；待逐版本公开证据 |
| 第三方独立复现 | — | 尚未发生，欢迎社区提交 |

当前发布状态是 **`IMPLEMENTED`**：Skill、协议资源、脚本、示例和 CI 已实现。它不是 `PROJECT_VERIFIED` 或 `COMMUNITY_VERIFIED`；只有对应证据完成并入库后才升级状态。

---

## 仓库结构

```text
jiaojie-skill/
├── SKILL.md                 # AI 首先读取的轻量工作流
├── agents/openai.yaml       # Codex / OpenAI 界面元数据
├── references/              # 协议、安全、多语言、领域与兼容细节
├── scripts/                 # 导出、接收、转换、扫描与验证工具
├── assets/
│   ├── templates/           # 人类交接与审计包模板
│   ├── schemas/             # JSON Schema
│   ├── vectors/             # 确定性测试向量
│   └── registry/            # 版本锁定的注册表数据
├── examples/                # 七领域公开演示
├── evals/                   # 连续性评分卡与复现契约
├── tests/                   # 离线自动测试
└── .github/                 # CI、Issue 与 PR 模板
```

核心 Skill 保持简短，普通交接只需读取 [`references/simple-workflow.md`](references/simple-workflow.md)。只有正式审计、旧格式转换、多语言歧义或领域特殊情况才按需加载其他参考。

---

## 它不是什么

- 不是无限记忆，也不保证平台没有截断输入；
- 不是逐字复制整段聊天；
- 不保存或推测隐藏思维；
- 不让旧会话越权控制新会话；
- 不用一个自评分数替代独立模型和人工复现；
- 不承诺所有 Runtime 已经通过同样等级的验证。

如果源会话已经缺失关键内容，正确结果是 `PARTIAL` 或 `UNKNOWN`，不是编造一个看起来完整的包。

---

## 贡献与社区

最有价值的贡献不是再写一份相似摘要模板，而是提交可复现的新证据：

- 新模型、语言与 Runtime 的真实运行记录；
- 能暴露连续性失败的新案例；
- 对现有协议、Schema、安全边界或转换器的修复；
- 第三方 Agent 对 Jiaojie 格式的实现；
- 独立盲评与失败复现。

开始前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)、[`COMMUNITY.md`](COMMUNITY.md) 和 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。协议变化遵循 [`GOVERNANCE.md`](GOVERNANCE.md)；安全问题不要公开建 Issue。

---

## 路线图

- [x] 人类优先的三档输出与对称导出/接收；
- [x] 意图演化、负知识、完整性和当前授权边界；
- [x] LCH 0.1 审计路径、Schema、哈希、转换器和安全扫描；
- [x] 七领域公开演示与确定性 CI；
- [ ] 五个主流模型的交叉发送/接收公开结果；
- [ ] 至少八个 Runtime 的版本化真实证据；
- [ ] 三位独立贡献者完成盲评和第三方复现；
- [ ] 社区共识形成后冻结稳定版 `1.0` 协议。

路线图中的未完成项不会出现在兼容矩阵的 ✅ 中。

---

## 致谢与许可

Jiaojie 借鉴了开放 Agent Skills 生态中“把工作交给下一位 Agent”的产品方向，并在 [`NOTICE.md`](NOTICE.md) 中记录参考项目和第三方数据来源。Jiaojie 的代码、文档和原创视觉不复制这些项目的实现或素材。

[MIT License](LICENSE) © 2026 Jordan Wei

> 让“交接一下”成为每个 AI 都理解的标准动作。
