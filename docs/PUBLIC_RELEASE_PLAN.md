# Public release preparation

Status: validation build prepared, broad public announcement pending HTTPS.

## Already prepared in the application

- `/validation` is a reproducible third-party validation entry point.
- The home page links to the validation entry point and warns that the instance is shared.
- The footer links to GitHub Issues for defect and usefulness reports.
- `/robots.txt` excludes API and mutable research surfaces from ordinary indexing.
- `/sitemap.xml` exposes only stable public pages.
- A responsive mobile baseline covers the header, search form, graph shell, context drawer, menu, action panel and touch-sized controls.
- Public responses include conservative security headers that do not claim HTTPS.
- Python smoke tests and a narrow 390×844 Playwright surface test cover the release entry point.
- FastAPI/Starlette/httpx are bounded to the tested compatibility family so a future dependency release does not silently change the verification harness.

## Current public URL

`http://219.94.244.239:8000/` is reachable without an account. It is useful for controlled human validation, but it is not the final public release URL because it is IP-based and HTTP-only.

The lack of authentication is intentional for the current validation phase. It also means that SQLite-backed projects and ledgers are a shared public surface. Do not enter private information or secrets.

## Required before broad announcement

1. Register a domain and point its DNS record at the VPS.
2. Set the final `server_name` in `deploy/nginx-dialexis.conf`.
3. Obtain and install a trusted TLS certificate with certbot.
4. Redirect port 80 to HTTPS and verify that all CSS, JavaScript and API requests remain same-origin HTTPS.
5. Add HSTS only after HTTPS and renewal have been verified.
6. Set `DIALEXIS_CONTACT` to a real public contact address or document the GitHub Issues channel as the sole contact route.
7. Confirm backup restore, resource limits, abuse/rate-limit policy and log rotation before announcing the URL widely.

## Release gate

Run locally:

```bash
./verify.sh
```

Then deploy only the commit whose SHA was written to `deploy/verified_sha.txt`:

```bash
git push origin main
ssh -i /home/handa/.ssh/dialexis_vps ubuntu@219.94.244.239 /opt/dialexis/deploy/vps_deploy.sh
```

After deployment, verify `/healthz`, `/validation?lang=ja`, `/robots.txt`, `/sitemap.xml`, Karl Marx, the person relation panel, Communist Manifesto lineage, combine, ledger return, and the narrow-screen scenario.

## Rollback principle

Keep each public change as a commit. If a deployment regresses a verified path, stop announcing the URL, identify the last verified commit, and deploy a deliberate revert or the last known-good commit through the same test gate. Do not reset or delete the shared database as a first response; preserve the failure evidence.
