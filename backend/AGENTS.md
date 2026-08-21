# Project AGENTS.md — TrustOffice

This project uses Railway for deployment.

## 🔴 Railway Deployment Protocol (MANDATORY)

> **This project deploys to Railway. Before ANY deployment or Railway operation:**

1. **Load the `railway-deploy` skill** via MCP: `mcp_skill_registry_load_skill('railway-deploy')`. Do NOT attempt Railway operations without this skill loaded.
2. **The Railway CLI is permanently disabled.** NEVER use `railway up`, `railway init`, `railway link`, or any `railway` CLI commands. Use `rwy` CLI (`~/bin/rwy`) or GraphQL only.
3. **Token:** `~/.hermes/secrets/railway-token.txt` — works for ALL projects.
4. **Deploy via:** `git push` (if auto-deploy connected) OR `rwy deploy <project>/<service> --commit <SHA> --yes`.
5. **Verify after deploy:** `rwy deployments <project>/<service> --n 1` must show `status == SUCCESS`. Then health-check the live URL.
6. **Do NOT report "deployed" without verification.** Jeff has corrected this multiple times.
7. **Run the deploy pre-flight gate:** `bash ~/.openclaw/workspace/SYSTEM/scripts/deploy-preflight.sh <brand> <project> --subagent`

**If you are a subagent:** Your orchestrator should have included the deploy gate context in your task. If not, load the `railway-deploy` skill before doing anything with Railway.

