# Release process

Only the maintainer creates releases. The initial public repository should be reviewed before any tag is pushed.

## Pre-release checklist

1. Review `git diff --check` and every untracked file;
2. run `python3 scripts/project_check.py`;
3. run the Agent Skills validator described in the review report;
4. confirm `evals/compatibility-matrix.json` contains no unsupported claim;
5. search for secrets, personal paths, private conversations and placeholder links;
6. update `CHANGELOG.md` and the versions in `assets/protocol-version.json`;
7. build the deterministic skill archive with `python3 tools/build_release.py`;
8. verify the SHA-256 file and inspect the ZIP member list;
9. install from the exact candidate commit in a clean temporary directory;
10. obtain maintainer approval before commit, push, tag, or GitHub Release creation.

## Version policy

- Skill releases use Semantic Versioning;
- protocol, Schema, receipt and projection versions change independently and are pinned in `assets/protocol-version.json`;
- breaking protocol changes are allowed in `0.x` but require a migration note;
- compatibility and evidence status are data changes and must not be inferred from the release number.

## Manual publication

After review, commit and push `main`, then create an annotated tag. Upload the generated ZIP and `.sha256` file from `dist/` to the GitHub Release. Do not commit `dist/` binaries to the repository.

The release notes must list known limitations and must not turn `NOT_RUN` cells into broad compatibility claims.
