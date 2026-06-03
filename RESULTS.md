# Privacy Policy Analysis Results

This document records the empirical results of evaluating real-world privacy policies using the Privacy Policy Analyzer. Analyses were conducted using directly supported LLM providers on **Google Gemini** (`gemini-2.5-flash`).

---

## 📊 Summary of Analyzed Policies

| Platform | Domain | Resolved Policy URL | Overall Score | Red Flags | Confidence | Analysis Time |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **GitHub** | `github.com` | [GitHub Privacy Statement](https://docs.github.com/site-policy/privacy-policies/github-privacy-statement) | **44.40 / 100** | 8 | 100% | 23.66s |
| **TikTok** | `tiktok.com` | [TikTok Privacy Policy](https://www.tiktok.com/legal/privacy-policy) | **41.41 / 100** | 15 | 100% | 36.90s |
| **Facebook** | `facebook.com` | [Meta Privacy Policy](https://www.facebook.com/privacy/policy/) | **40.15 / 100** | 9 | 100% | 28.62s |

---

## 🔍 Detailed Breakdown per Platform

### 1. GitHub (Score: 44.40/100)

> [!NOTE]
> GitHub provides relatively transparent data sharing disclosures and clear lawful bases, but scores extremely poorly on retention timelines and cross-border safeguards in user-facing summaries.

* **Top Strengths:**
  1. **Third Parties & Processors** (`8.5/10`) — Detailed processor disclosures and joint-controller roles are clearly demarcated.
  2. **Transparency & Notice** (`8.0/10`) — Standard simplified language with comprehensive version notices and clear contacts.
  3. **Lawful Basis & Purpose** (`7.5/10`) — Well-articulated data processing purposes and legitimate business interests.
* **Top Risks:**
  1. **Retention & Deletion** (`0.0/10`) — Criticized for indefinite retention clauses (e.g., "retained as long as your account is active").
  2. **Cross-Border Transfers** (`0.5/10`) — Extremely vague transfer mechanism safety disclosures in main text chunks.
  3. **Security & Breach** (`1.0/10`) — Lack of concrete technical and organizational safety measures detailed in the text excerpt analyzed.

---

### 2. TikTok (Score: 41.41/100)

> [!WARNING]
> TikTok suffers from a massive volume of Red Flags (15 distinct flags detected). While transparent about *why* they collect data, their security standards and user-redress frameworks remain highly problematic under global scoring rubrics.

* **Top Strengths:**
  1. **Lawful Basis & Purpose** (`7.0/10`) — Purposes of processing are detailed but heavily geared toward personalized content.
  2. **Secondary Use & Limits** (`6.67/10`) — Stated boundaries on auxiliary features.
  3. **Transparency & Notice** (`6.67/10`) — Highly structured layout despite massive length.
* **Top Risks:**
  1. **Security & Breach** (`0.0/10`) — Analyzed chunks contained zero actionable breach details or concrete technical guardrails.
  2. **Retention & Deletion** (`2.0/10`) — "Keep as long as necessary" phrasing used frequently without specific schedules.
  3. **User Rights & Redress** (`2.67/10`) — Complex mechanisms to object or request erasure for global users outside EEA/California jurisdictions.

---

### 3. Facebook / Meta (Score: 40.15/100)

> [!CAUTION]
> Meta's privacy policy is highly structured and written in plain language (high transparency scoring), yet the underlying substance scores heavily against user protection—particularly on indefinite data retention and aggressive cross-border transfers.

* **Top Strengths:**
  1. **Transparency & Notice** (`7.0/10`) — Excellent usage of plain-language headings, bullet points, and interactive cookie control guidance.
  2. **Lawful Basis & Purpose** (`5.67/10`) — Categorized lists of purposes.
  3. **Secondary Use & Limits** (`5.67/10`) — Stated boundaries on ad rendering vs. diagnostic telemetry.
* **Top Risks:**
  1. **Retention & Deletion** (`0.67/10`) — Extremely low scoring due to massive loops of indefinite storage policies.
  2. **Security & Breach** (`1.67/10`) — Highly generic security assertions with no robust technical benchmarks.
  3. **Cross-Border Transfers** (`2.0/10`) — Aggressive globally dispersed storage notices with standard contractual clauses (SCC) obscured in deeply nested external links.

---

## 🚀 Execution Commands

To reproduce these exact results, configure your `.env` with a `GEMINI_API_KEY` and run:

```bash
# Analyze GitHub
uv run python src/main.py --url https://github.com --model gemini-2.5-flash --report summary --max-chunks 2

# Analyze TikTok
uv run python src/main.py --url https://tiktok.com --model gemini-2.5-flash --report summary --max-chunks 3

# Analyze Facebook
uv run python src/main.py --url https://facebook.com --model gemini-2.5-flash --report summary --max-chunks 3
```
