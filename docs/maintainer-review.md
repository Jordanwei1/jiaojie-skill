# Maintainer review and first publication

Nothing in this checklist commits, pushes, tags, or publishes automatically.

## 1. Review the product surface

- `README.md` — Chinese default, product promise, demo, install, evidence status;
- `README_EN.md` and the four other translations;
- `SKILL.md` — trigger accuracy and the smallest-sufficient-format behavior;
- `SECURITY.md`, `GOVERNANCE.md`, `CONTRIBUTING.md`, `NOTICE.md`;
- `evals/compatibility-matrix.json` — all untested cells must remain `NOT_RUN`;
- `evals/results/` — local deterministic and discovery evidence only;
- `assets/hero.gif` — original Jiaojie visual;
- `git status --short` — ensure every intended file is understood.

## 2. Re-run locally

```bash
python3 scripts/project_check.py
python3 /path/to/skill-creator/scripts/quick_validate.py .
npx --yes skills add . --list
python3 tools/build_release.py
cd dist && shasum -a 256 -c jiaojie-skill-0.1.0.zip.sha256
```

The `skill-creator` validator path depends on the local Agent installation and is therefore intentionally not hard-coded into repository CI.

## 3. Inspect publication safety

- no `.env`, private key, Token, password, cookie, personal conversation or client artifact;
- no `/Users/...`, `file://` or temporary local path in published content;
- no copied competitor image, copywriting, example dialogue or source code;
- all test conversations are synthetic and marked `GOLD_CANDIDATE`;
- `PARTIAL`, `NOT_RUN`, `IMPLEMENTED` and third-party status are not inflated;
- `dist/` and Python caches remain ignored.

## 4. First manual commit

After approval only:

```bash
git add .
git status --short
git diff --cached --check
git commit -m "feat: open source Jiaojie context handoff skill"
git push -u origin main
```

Review the staged diff before the commit. The local release archive is ignored and will not be added by `git add .`.

## 5. GitHub repository settings

- About description: `Switch models. Keep the work. Open context handoff for continuous AI collaboration across chats, models, devices, and languages.`
- Website: leave empty until a real project site exists;
- Topics: `agent-skills`, `ai-agents`, `context-handoff`, `llm`, `codex`, `claude-code`, `cursor`, `multilingual`, `context-engineering`, `open-source`;
- enable Issues, Discussions and private vulnerability reporting;
- set `main` as default branch;
- protect `main` after the initial commit: require PR, passing `validate`, no force-push, no deletion;
- add a social preview only from `promo/social-card.png`.

## 6. Initial release

After the public commit and Actions pass:

1. create annotated tag `v0.1.0` on the reviewed commit;
2. push the tag;
3. create the GitHub Release;
4. upload `dist/jiaojie-skill-0.1.0.zip` and its `.sha256` file;
5. copy limitations from `CHANGELOG.md` and do not add untested compatibility claims.

Do not mark the project `PROJECT_VERIFIED` or `COMMUNITY_VERIFIED` during the initial release.
