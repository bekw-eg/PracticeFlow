# Supply-chain security

## Invariants and CI gate

Production and development Docker base images are referenced by immutable SHA-256
digest. The adjacent comment records the reviewed human-readable version. The
same rule applies to PostgreSQL, Redis, MinIO, Caddy and every GitHub Actions
`uses:` reference. `scripts/verify_container_security.py` fails if a Docker
base/Compose image is mutable, an action is not a 40-character commit SHA, a
final Dockerfile process is root, Compose explicitly runs as root/privileged or
mounts `docker.sock`, or a sensitive build/Compose value is literal.

The `Supply chain security` workflow builds the production backend and frontend
images locally in the runner. It does not push an image or access GitHub
Secrets, a registry credential, production data, or a deployment `.env` file.
It produces an SPDX JSON SBOM with Syft `v1.51.1` and a JSON CVE report with
Trivy `v0.65.0` for each image. Reports and test JUnit XML are workflow
artifacts; they contain package and vulnerability metadata, never CI
environment values or secrets.

Trivy is a blocking gate for every High or Critical CVE, including unfixed
CVEs. The only exclusion mechanism is the reviewed, temporary `.trivyignore`
file described below. Make `Supply chain security / Build, attest and scan
production images` a required status check in the repository ruleset.

## Updating a pinned image or action

1. Review the upstream release and its compatibility/security notes.
2. Resolve the candidate manifest-list digest, then use `repository@sha256:...`
   in every relevant `FROM` or `image:` entry. Preserve a nearby version
   comment. For example:

   ```bash
   docker buildx imagetools inspect postgres:16-alpine --format '{{.Manifest.Digest}}'
   ```

3. For GitHub Actions, resolve the selected release tag to a complete commit
   SHA, for example `git ls-remote https://github.com/actions/checkout.git
   refs/tags/v4.2.2`. Never use the tag itself in `uses:`.
4. Run the local checks and rebuild both images. Submit the digest/action update
   and any resulting SBOM/CVE review together. Dependabot opens weekly updates
   for Docker, Actions, pip and npm dependencies; human review still owns the
   digest and CVE decision.

The build uses `npm ci` without modifying `package-lock.json`; Python package
versions remain in the existing requirements files. This gives repeatable
application dependency resolution and immutable base-image selection. Debian
APT packages are still fetched from the base distribution's repository at build
time, so bit-for-bit hermetic rebuilds additionally require an organisation
managed, snapshot-pinned APT mirror; that infrastructure is intentionally not
created by this repository.

## Local validation, SBOM and CVE review

```bash
python scripts/verify_container_security.py
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.test.yml config --quiet
docker compose -f docker-compose.e2e.yml config --quiet
docker compose -f docker-compose.prod.yml -f deployment/caddy/docker-compose.caddy.yml config --no-interpolate --quiet

docker build --pull=false -t practiceflow-backend:local backend
docker build --pull=false -t practiceflow-frontend:local frontend

mkdir -p artifacts/sbom artifacts/trivy
syft practiceflow-backend:local -o spdx-json=artifacts/sbom/practiceflow-backend.spdx.json
syft practiceflow-frontend:local -o spdx-json=artifacts/sbom/practiceflow-frontend.spdx.json
jq -e '.spdxVersion and (.packages | type == "array")' artifacts/sbom/practiceflow-backend.spdx.json
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --ignorefile .trivyignore \
  --format json --output artifacts/trivy/practiceflow-backend.json practiceflow-backend:local
```

Use the corresponding frontend commands to inspect that image. Treat generated
`artifacts/` files as review output, not source input; do not add `.env`, an
image `inspect` dump, or deployment log to them. In GitHub, download the
`production-image-supply-chain-artifacts` artifact from the workflow run and
verify the same SPDX fields before approving a release.

## Temporary CVE exceptions

An exception is allowed only when a remediation cannot yet be deployed and a
ticket/owner has accepted the risk. Add exactly one CVE identifier with the
required preceding metadata, for example:

```text
# owner=@platform-security | expires=2026-09-30 | reason=upstream-fix-tracked-in-SEC-123
CVE-2026-12345
```

Keep the expiry short, link the remediation ticket in the pull request, and
remove the entry immediately after updating the image. The local policy check
rejects undocumented, malformed and expired exceptions. Do not exempt a broad
package, severity, image, or unfixed-CVE class.

## Keyless release signature

`.github/workflows/release-sign.yml` is deliberately a manual template. By
default it validates nothing and makes no registry request. It never builds or
pushes an image. After a reviewed image has been pushed by the deployment
release process, dispatch it with its immutable reference, for example
`ghcr.io/example/practiceflow-backend@sha256:<digest>`, and set
`perform_sign=true`. GitHub supplies the short-lived OIDC identity and Cosign
creates a keyless signature; no long-lived signing key or registry password is
stored in this repository.

After signing, verify it with the expected GitHub Actions identity and issuer:

```bash
cosign verify \
  --certificate-identity "https://github.com/<owner>/<repository>/.github/workflows/release-sign.yml@refs/heads/<protected-branch>" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/<owner>/practiceflow-backend@sha256:<digest>
```

Configure registry permissions and protected-environment policy in the real
GitHub repository before first use. The current checkout has neither a
registry target nor credentials, so signing is intentionally not invoked here.
