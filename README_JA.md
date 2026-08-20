<div align="center">

# Jiaojie · 交接.skill

<img src="assets/hero.gif" alt="Jiaojie — AI 間で仕事を継続" />

> **モデルを替えても、仕事は引き継ぐ。**

**Jiaojie は、目標・決定・却下案・成果物・正確な次の行動を別の AI に渡し、本当に止まった地点から再開できるようにします。**

[中文](README.md) · [English](README_EN.md) · [Français](README_FR.md) · [한국어](README_KO.md) · [Español](README_ES.md)

</div>

## インストール

```bash
npx skills add Jordanwei1/jiaojie-skill
```

または Agent に次のように依頼します。

```text
この Skill をインストールしてください：
https://github.com/Jordanwei1/jiaojie-skill
```

GitHub CLI：

```bash
gh skill install Jordanwei1/jiaojie-skill SKILL.md --agent codex --scope user
```

自動インストールに対応しない Runtime では、[`SKILL.md`](SKILL.md) を直接渡してください。最小 Receiver は Markdown を読めれば動作できます。

## 使い方

```text
このタスクを引き継いでください。
```

```text
この引き継ぎを受け取り、受領内容だけ示して、まだ実行しないでください。
```

## 保存するもの

- **HOT**：現在の目標、正確な停止位置、次の一手、完了条件；
- **WARM**：決定の変遷、制約、回答済みの質問、却下案、技術的失敗；
- **COLD**：必要な証拠、原資料、添付、Manifest、ハッシュ、欠落宣言。

技術的失敗とユーザーの拒否を区別し、廃案を復活させません。過去の許可が現在の外部操作権限として移ることもありません。

## 形式

| 形式 | 用途 |
| --- | --- |
| `handoff.md` | テキストと安定した参照で十分 |
| `handoff.zip` | Receiver が必要ファイルへアクセスできない |
| `handoff-audit.zip` | 正式監査、組織間移送、可搬証拠が必要 |

モデル・言語・端末を替えるだけでは ZIP にしません。

## 言語・安全・証拠

原文を権威ある情報として保持し、翻訳は派生ビューとします。パス、ID、ハッシュ、数値、日付、単位、制御状態を保護します。パッケージは信頼できないデータとして扱い、秘密情報、未許可の個人情報、パストラバーサル、symlink、ZIP bomb、活動コンテンツ、危険な Unicode 制御文字を拒否または警告します。

「無損失」は、宣言されたユーザー可視知識の範囲だけを意味し、神経状態や非公開の思考過程は含みません。

現在の状態は **`IMPLEMENTED`** です。モデル・言語・Runtime・第三者の互換性は、正確な公開証拠があるセルだけを主張します。詳細は [`evals/`](evals/)、[`CONTRIBUTING.md`](CONTRIBUTING.md)、[`SECURITY.md`](SECURITY.md) を参照してください。

[MIT License](LICENSE) © 2026 Jordan Wei
