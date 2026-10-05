# Reviewed branch integration — 2026-10-05

The integration branch preserves the owner-authored commits from PRs #29
(group review and private PPTX presentations) and #31 (disciplines, topics and
private teaching materials). It also snapshots the outstanding application
changes from the original checkout: bulk student membership, teacher review
queue, deadline notifications, export glyph fixes and completed ru/kk/en UI
translations. Local credentials, real documents, generated validation reports,
test databases and temporary dependencies are excluded. The original checkout
is preserved.

All new commits use `bekw-eg` and
`217148214+bekw-eg@users.noreply.github.com` for Author and Committer. The shared
Git hook checks both identities before committing. Existing upstream and bot
history is preserved; dependency updates are reviewed and committed separately
by the owner, without relabelling the original bot commits.

## Dependency PR review

| Existing PR | Reviewed disposition |
| --- | --- |
| #3, #5, #9 | Checkout 7.0.1, artifact upload 7.0.1 and setup-node 7.0.0, pinned to verified release SHAs |
| #6, #8 | Cosign installer 4.1.2 and SBOM action 0.24.0, pinned to verified release SHAs |
| #7, #10, #18 | cryptography 50.0.1, sentry-sdk 2.68.1 and uvicorn 0.52.4 |
| #11, #12 | pip-audit minimum 2.10.1 and Ruff 0.16.4 |
| #13, #16 | Already superseded by the consistent Tiptap 3.31.4 dependency set in PR #29 |
| #14 | Vitest 4.1.11 already included in PR #29 |
| #15, #17 | React Vite plugin 6.1.2 (supersedes 6.1.0) and TypeScript 7.0.2; build compatibility is checked together |
| #25 | Replace the old Debian Trixie base with a currently resolved Python 3.12 Bookworm manifest and install distribution security updates |
| #27, #30 | Resolve current Node 22 Alpine and unprivileged Nginx 1.30.4 Alpine manifests from the upstream registry |

Bot PRs are superseded only after the replacement integration is confirmed in
`main`. New application/API changes require no additional database revision;
the migrations from #29 and #31 remain in their original order.

## Supply-chain remediation

The expired `.trivyignore` entries are removed. High/Critical scanning remains
blocking, includes unfixed vulnerabilities and produces SPDX SBOMs and JSON
scan reports for both production images. No risk exception is renewed.
The discontinued Trivy 0.65.0 download is replaced by
[Trivy 0.75.0](https://github.com/aquasecurity/trivy/releases/tag/v0.75.0).
Its Linux archive checksum is fixed in the workflow and verified before use.
Both scans must succeed and produce JSON reports for the final gate to pass.

The test-only MinIO image is compiled from pinned upstream source commits:

- [MinIO RELEASE.2025-10-15T17-29-55Z](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z),
  commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`, including the
  [session-policy bypass fix](https://github.com/minio/minio/security/advisories/GHSA-jjjj-jwhf-8rgr).
- [mc RELEASE.2025-08-13T08-35-41Z](https://github.com/minio/mc/releases/tag/RELEASE.2025-08-13T08-35-41Z),
  commit `7394ce0dd2a80935aded936b09fa12cbb3cb8096`.

Go and Alpine base manifests are immutable. Go module checksum verification
remains enabled; upstream AGPL licenses are included in the image. The image
runs as UID/GID 10001, keeps the bucket private and is used only by the isolated
E2E stack. Production S3 configuration is unchanged.
The first source build may take longer, so E2E has a 40-minute job limit.

Validation results and any remaining merge blockers are recorded in the
integration pull request. Merge requires successful CI and supply-chain scans
at the reviewed head SHA. Rollback uses a reviewed revert PR; no branch
protection or validation gate is bypassed.
