# Cost Estimates — FindIt

Monthly cost breakdown for running FindIt on Azure, based on the current deployment configuration.

## Deployment Configuration

| Setting | Value |
|---|---|
| Region | East US |
| Container Apps | Scale 0–10, 0.5 vCPU / 1 GB RAM each |
| Container Registry | Basic SKU |
| Storage | Standard LRS, Hot tier |
| Log Analytics | Pay-as-you-go, 30-day retention |
| AI Model | Google Gemini (`gemini-3-flash-preview`) |

---

## 1. Azure Container Apps (Backend + Frontend)

| Resource | Free Allowance (Monthly) | Unit Price (post-free) |
|---|---|---|
| vCPU (compute) | 180,000 vCPU-seconds | $0.000024 / vCPU-second |
| Memory | 360,000 GiB-seconds | $0.000003 / GiB-second |
| HTTP Requests | 2,000,000 | $0.40 / million requests |

Both apps are configured with `minReplicas: 0`, so they **scale to zero** when idle and incur no compute cost.

| Scenario | Est. Monthly Cost |
|---|---|
| Light use (scales to zero, <50 req/day) | ~$0 (within free tier) |
| Moderate use (~500 req/day, always-on) | ~$15–25 |

> The free tier covers ~50 vCPU-hours and 100 GiB-hours per month — enough for personal or demo use.

---

## 2. Azure Container Registry (Basic SKU)

| Item | Cost |
|---|---|
| Base price | ~$5.00/month |
| Included storage | 10 GB |
| Additional storage | ~$0.003/GB/day |

The two container images (`memory-backend`, `memory-frontend`) are ~200 MB each, well within the 10 GB included storage.

**This is the only fixed monthly cost (~$5).**

---

## 3. Azure Blob Storage (Standard LRS, Hot Tier)

| Item | Rate |
|---|---|
| Storage | $0.018/GB/month |
| Write operations | $0.065/10K operations |
| Read operations | $0.005/10K operations |

| Videos Stored | Est. Monthly Cost |
|---|---|
| 1 GB (5–10 short videos) | ~$0.02 |
| 10 GB (50+ videos) | ~$0.18 |
| 100 GB | ~$1.80 |

> Video uploads are the main storage driver. No file size limits are enforced by the app.

---

## 4. Log Analytics Workspace

| Item | Rate |
|---|---|
| Data ingestion | ~$2.76/GB |
| Free allowance | 5 GB/month |
| Retention | 31 days (free) |

For a small app with light traffic, log volume is typically <1 GB/month — well within the free tier.

| Scenario | Est. Monthly Cost |
|---|---|
| Light use (<1 GB logs) | ~$0 |
| Moderate use (5–10 GB logs) | ~$5–15 |

---

## 5. Google Gemini API (External)

Model: `gemini-3-flash-preview`

| Item | Rate |
|---|---|
| Input tokens | $0.50 / 1M tokens |
| Output tokens | $3.00 / 1M tokens |
| Free tier | ~20 requests/day (no billing enabled) |

Each voice query uses ~1K–5K tokens. Each video analysis uses ~10K–50K tokens.

| Usage | Est. Monthly Cost |
|---|---|
| Free tier (≤20 req/day) | $0.00 |
| With billing (~500 req/month) | ~$1–3 |
| Heavy (~5,000 req/month) | ~$10–20 |

> Enable billing in [Google AI Studio](https://aistudio.google.com/) to lift the 20 req/day limit.

---

## Total Monthly Estimate

| Component | Light / Personal Use | Moderate Use |
|---|---|---|
| Container Apps (2 apps) | $0 (free tier) | ~$15–25 |
| Container Registry | $5.00 | $5.00 |
| Blob Storage (5 GB) | ~$0.09 | ~$0.09 |
| Log Analytics | $0 (free tier) | ~$2–5 |
| Gemini API | $0 (free tier) | ~$1–3 |
| **Total** | **~$5/month** | **~$25–40/month** |

For personal or demo use with scale-to-zero and the Gemini free tier, the only fixed cost is the Container Registry at ~$5/month. Everything else is usage-based and likely stays within free tiers.

---

## Cost Optimization Tips

1. **Keep `minReplicas: 0`** — Scale-to-zero eliminates idle compute charges (trade-off: ~30s cold start).
2. **Use Gemini free tier during development** — 20 requests/day is enough for testing.
3. **Monitor blob storage growth** — Large video uploads can accumulate quickly. Delete unused videos via the My Videos page.
4. **Review Log Analytics ingestion** — If costs grow, filter verbose logs or switch to the Auxiliary Logs tier ($0.15/GB).
5. **Consider downgrading ACR** — The Basic SKU ($5/month) is the minimum. There is no free tier for ACR.

---

*Prices are based on Azure public pricing as of March 2026 for the East US region. Actual costs may vary. Use the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) for precise quotes.*
