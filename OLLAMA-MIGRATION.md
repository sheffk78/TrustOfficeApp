# TrustOffice AI Backbone — Provider Migration

**Date:** April 30, 2026 (initial), updated May 30, 2026
**Status:** Production — OpenRouter (Gemini) primary, Claude fallback. Live and stable.

---

## What Changed (May 2026 Update)

The AI backend has been **migrated from Claude-only to OpenRouter (Gemini) primary with Claude fallback**.

- **Primary provider:** OpenRouter → Google Gemini 2.5 Flash (drafting) / Gemini 2.5 Pro (suggestions)
- **Fallback provider:** Claude (Anthropic API) — kicks in automatically if OpenRouter fails
- **Health status:** ✅ Both providers available and healthy (verified May 30, 2026)
- **Quality:** Tested 5 minutes drafts — all pass quality checks (WHEREAS/RESOLVED format, proper length, legal structure, cautions)
- **Customer complaints:** Zero AI-related complaints in support inbox (May 2026)
- **Cost savings:** ~$82/mo estimated (previous $80-100/mo Claude → ~$8/mo OpenRouter + minimal Claude fallback)

---

## New Files

| File | Purpose |
|---|---|
| `ollama_client.py` | Raw Ollama API wrapper (generate + chat APIs) |
| `ai_client.py` | Unified provider — Ollama → fallback to Claude |
| `ai_service.py` | Updated to use `ai_client.py` instead of `claude_client.py` directly |

---

## Environment Variables

Add these to Railway (production) and `.env` (local):

```
# AI Provider Configuration
AI_PRIMARY_PROVIDER=ollama

# Ollama Server
# Option A: Local dev
OLLAMA_HOST=http://localhost:11434

# Option B: Cloud instance (recommended for production)
# OLLAMA_HOST=https://ollama-[your-instance].railway.app

# Model Selection
OLLAMA_MODEL_DRAFT=qwen3.5:9b         # Minutes drafting (~1200 tokens)
OLLAMA_MODEL_QUICK=qwen3.5:9b         # Governance suggestions (~400 tokens)

# Claude still needed as fallback
CLAUDE_API_KEY=sk-ant-api03-...        # Keep this set
```

---

## Production Deployment Architecture

### Option A: Ollama on a Cloud GPU Instance (Recommended)

For production, Railway containers share resources and don't have GPU acceleration. The best approach is a dedicated Ollama instance.

**Recommended setup:**
1. **Ollama Cloud** — Ollama Max already provides kimi-k2.6 and deepseek-v4-pro via cloud
2. **OR Dedicated VPS** — Run Ollama on a cheap Hetzner/AWS/GCP instance with the `ollama serve` endpoint exposed
3. **Tunnel approach** (development only) — Use ngrok or similar to expose local Ollama to Railway

**Architecture:**
```
User → app.trustoffice.app → Railway (FastAPI)
                                   ↓
                            OLLAMA_HOST (cloud GPU)
                                   ↓
                       qwen3.5:9b / kimi-k2.6 / deepseek-v4-pro
                                   ↓ (if fails)
                            call_claude_sonnet / call_claude_haiku
                                   ↓
                            Anthropic API
```

**Security note:** Never expose Ollama on 0.0.0.0:11434 without authentication. Use Railway private networking or set OLLAMA_HOST to an internal URL with API key headers.

---

## Model Selection Guide

| Task | Recommended Model | Why |
|---|---|---|
| Minutes drafting | `qwen3.5:9b` | Strong formal writing, handles JSON well, fits in 32GB RAM |
| Minutes drafting (premium) | `kimi-k2.6:cloud` | Best output quality via Ollama Max (~54 IQ points) |
| Governance suggestions | `qwen3.5:9b` | Fast, good at structured JSON, lightweight |
| Fallback (always) | Claude Sonnet | Guaranteed quality, reliable JSON output |

**Testing strategy:** Start with `qwen3.5:9b` locally, evaluate output quality. If quality is not adequate, upgrade to `kimi-k2.6:cloud` or keep using Claude for drafting and use Ollama only for suggestions.

---

## Testing Checklist (Before Production Deploy)

- [ ] Set `OLLAMA_HOST` and `OLLAMA_MODEL_DRAFT` env vars
- [ ] Test `GET /api/ai/health` — should show `"providers.ollama.available": true`
- [ ] Test minutes drafting via UI (create minutes → AI Draft)
- [ ] Test governance suggestions via Dashboard (AI Recommendations card)
- [ ] Test fallback: temporarily stop Ollama, verify Claude handles requests
- [ ] Verify no regressions in JSON parsing (some models wrap in markdown code blocks)
- [ ] Run existing pytest suite: `pytest backend/tests/test_ai_endpoints.py -v`

---

## Known Limitations

1. **Railway cannot reach localhost** — The local Ollama instance (on this machine) is not reachable from Railway. For production you need a cloud-hosted Ollama or Ollama Max cloud models.

2. **Cloud models are "cloud"-tagged** — Models like `kimi-k2.6:cloud` and `deepseek-v4-pro:cloud` run via Ollama's cloud service, not locally. They require an Ollama Max subscription.

3. **Temperature sensitivity** — Formal minutes drafting works best at `temperature=0.2`. Higher temps produce flowery language; lower temps get repetitive.

4. **JSON consistency** — All tested models occasionally wrap JSON in markdown code blocks. The `ai_service.py` parser handles this (strips ```json and ```).

---

## Rollback Plan

If Ollama quality is insufficient:

1. Set `AI_PRIMARY_PROVIDER=claude` in Railway env vars
2. No code changes needed — `ai_client.py` automatically routes to Claude
3. All existing `OLLAMA_*` env vars are ignored when primary is Claude
4. Restart Railway services

**Instant rollback:** One env var change, one restart. Zero code deploy.

---

## Cost Comparison

| Provider | Monthly Cost | Quality | Reliability |
|---|---|---|---|
| Claude API (Sonnet+Haiku) | $80-100 | Excellent | Excellent |
| Ollama Cloud (kimi-k2.6) | $100 flat | Excellent | Good |
| Ollama Local (qwen3.5:9b) | $0 | Good | Depends on hardware |
| Ollama + Claude fallback | ~$10-20 (fallback only) | Excellent | Best of both |

**Recommendation:** Run in Ollama-first + Claude fallback mode. Monitor fallback rate. If fallback rate exceeds ~30% of calls, switch back to Claude-only or upgrade to kimi-k2.6:cloud.

---

## 1-Month Review Plan

Automated cron job set up for **May 30, 2026** to review:
- Fallback rate (Claude usage vs Ollama usage via logs)
- Customer complaints about AI quality
- Output quality sample review (spot-check 10 random minutes drafts)
- Cost savings achieved
- Model performance (latency, timeout rate)

See `CRON-OLLAMA-REVIEW` job for details.
