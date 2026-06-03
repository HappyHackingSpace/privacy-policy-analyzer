# Privacy Policy Analyzer - Test Results

This document contains the analysis results for **Facebook** and **TikTok** privacy policies using the newly refactored production-grade CLI tool.

---

## 1. Facebook Analysis Results

*   **Target Website:** `https://facebook.com`
*   **Resolved Privacy URL:** `https://www.facebook.com/privacy/policy/?entry_point=facebook_page_footer`
*   **LLM Model Used:** `openai/gpt-oss-120b:free` (OpenRouter)
*   **Total Chunks Analyzed:** 6 (5 valid chunks aggregated)

### Score & Overview
*   **Overall Privacy Score:** `42.16 / 100` (Moderate risk profile)
*   **Confidence Level:** `1.0`
*   **Total Red Flags Identified:** `20`

### Top Strengths
1.  **Lawful Basis & Purpose:** `5.8 / 10`
2.  **Transparency & Notice:** `5.8 / 10`
3.  **Collection & Minimization:** `5.2 / 10`

### Top Risks
1.  **Retention & Deletion:** `2.8 / 10` (High Risk)
2.  **User Rights & Redress:** `3.2 / 10` (High Risk)
3.  **Sensitive Children, Ads & Profiling:** `3.2 / 10` (High Risk)

---

## 2. TikTok Analysis Results

*   **Target Website:** `https://tiktok.com`
*   **Resolved Privacy URL:** `https://www.tiktok.com/legal/privacy-policy-row`
*   **LLM Model Used:** `openai/gpt-oss-120b:free` (OpenRouter)
*   **Total Chunks Analyzed:** 4 (2 valid chunks aggregated)

### Score & Overview
*   **Overall Privacy Score:** `49.9 / 100` (Moderate risk profile, slightly better than Facebook)
*   **Confidence Level:** `1.0`
*   **Total Red Flags Identified:** `9`

### Top Strengths
1.  **Lawful Basis & Purpose:** `6.5 / 10`
2.  **Third Parties & Processors:** `6.5 / 10`
3.  **User Rights & Redress:** `6.0 / 10`

### Top Risks
1.  **Retention & Deletion:** `3.0 / 10` (High Risk)
2.  **Security & Breach:** `3.0 / 10` (High Risk)
3.  **Cross Border Transfers:** `3.5 / 10` (Medium-High Risk)

---

## 3. Performance & System Benchmarks

| Metric | Facebook (`https://facebook.com`) | TikTok (`https://tiktok.com`) |
| :--- | :--- | :--- |
| **Discovery Time** | 1.60s | 5.11s (Discovered via Sitemap) |
| **Fetching Time** | 3.50s | 1.97s |
| **LLM Analysis Time** | 114.72s | 59.91s |
| **Total Duration** | 119.83s | 66.99s |
| **Average Per Chunk** | 19.12s | 14.98s |
| **Text Characters** | 48,763 chars | 31,001 chars |

---

## 4. Key Takeaways
1.  **Robust Sitemap Discovery:** The new scoring and sitemap heuristics successfully located TikTok's exact privacy policy at `https://www.tiktok.com/legal/privacy-policy-row` under 5.11s.
2.  **Parallel Execution & Rate Limits:** The multi-threaded pipeline analyzed multiple policy chunks simultaneously. The integrated `tenacity` exponential retry logic flawlessly handled rate limits on the free tier backend.
3.  **Clean Output Architecture:** Standardized error outputs (`click.secho(..., err=True)`) kept stdout completely clean, allowing accurate piping of the output JSON string.
