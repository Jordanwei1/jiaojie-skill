<div align="center">

# Jiaojie · 交接.skill

<img src="assets/hero.gif" alt="Jiaojie — AI 사이에서 작업 연속성 유지" />

> **모델을 바꿔도, 작업은 이어집니다.**

**Jiaojie는 목표, 결정, 폐기된 선택지, 산출물, 정확한 다음 행동을 다른 AI에 넘겨 실제로 멈춘 지점부터 계속하게 합니다.**

[中文](README.md) · [English](README_EN.md) · [Français](README_FR.md) · [日本語](README_JA.md) · [Español](README_ES.md)

</div>

## 설치

```bash
npx skills add Jordanwei1/jiaojie-skill
```

또는 Agent에게 다음과 같이 요청하세요.

```text
이 Skill을 설치해 주세요:
https://github.com/Jordanwei1/jiaojie-skill
```

GitHub CLI:

```bash
gh skill install Jordanwei1/jiaojie-skill SKILL.md --agent codex --scope user
```

자동 설치를 지원하지 않는 Runtime에는 [`SKILL.md`](SKILL.md)를 직접 제공하세요. 최소 Receiver는 Markdown만 읽을 수 있으면 됩니다.

## 사용

```text
이 작업을 인계해 주세요.
```

```text
이 인계를 받고 수신 확인만 보여 주세요. 아직 실행하지 마세요.
```

## 보존하는 내용

- **HOT**: 현재 목표, 정확한 중단 지점, 다음 행동, 완료 기준;
- **WARM**: 결정 변화, 제약, 이미 답한 질문, 거부된 경로와 기술 실패;
- **COLD**: 필요한 증거, 원자료, 첨부, Manifest, 해시, 누락 선언.

기술 실패와 사용자 거부를 구분하고 폐기된 선택지를 되살리지 않습니다. 과거의 허가를 현재의 외부 작업 권한으로 넘기지도 않습니다.

## 형식

| 형식 | 사용 조건 |
| --- | --- |
| `handoff.md` | 텍스트와 안정적인 참조만으로 충분 |
| `handoff.zip` | Receiver가 필수 파일에 접근할 수 없음 |
| `handoff-audit.zip` | 공식 감사, 조직 간 전달, 이동 가능한 증거 필요 |

모델, 언어 또는 장치 변경만으로 ZIP이 필요해지는 것은 아닙니다.

## 언어, 보안, 증거

원문을 권위 있는 정보로 유지하고 번역은 파생 뷰로 취급합니다. 경로, ID, 해시, 숫자, 날짜, 단위와 제어 상태를 보호합니다. 모든 패키지는 신뢰할 수 없는 데이터로 처리하며 비밀, 승인되지 않은 개인정보, 경로 탈출, symlink, ZIP bomb, 활성 콘텐츠, 위험한 Unicode 제어 문자를 거부하거나 경고합니다.

“무손실”은 선언된 사용자 가시 지식 경계에서의 연속성만 뜻하며, 신경 상태나 비공개 사고 과정은 포함하지 않습니다.

현재 상태는 **`IMPLEMENTED`** 입니다. 모델, 언어, Runtime, 제3자 호환성은 정확한 공개 증거가 있는 셀만 주장합니다. [`evals/`](evals/), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md)를 참고하세요.

[MIT License](LICENSE) © 2026 Jordan Wei
