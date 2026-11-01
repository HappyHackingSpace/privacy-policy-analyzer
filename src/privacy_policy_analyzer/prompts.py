from typing import Final
from textwrap import dedent

__all__ = ["SYSTEM_SCORER", "build_user_prompt"]

SYSTEM_SCORER: Final[str] = (
    "You must return one valid JSON object that strictly matches the user's schema. "
    "Do not include any text outside JSON. Do not add extra fields."
)

_USER_SCORING_JSON: Final[str] = """
Act as a senior global privacy/compliance auditor. Given a privacy policy excerpt,
return ONE JSON object with category scores (0–10), concise rationales, red flags,
and optional evidence quotes. Be jurisdiction-agnostic yet globally aware of widely
recognized principles (e.g., purpose limitation, transparency, user rights, security,
third-party processing, retention, cross-border safeguards, children/sensitive data).
Do not opine on legal compliance—assess disclosure quality and user-protection clarity.

Schema (required fields):
{
  "scores": {
    "lawful_basis_and_purpose": int,
    "collection_and_minimization": int,
    "secondary_use_and_limits": int,
    "retention_and_deletion": int,
    "third_parties_and_processors": int,
    "cross_border_transfers": int,
    "user_rights_and_redress": int,
    "security_and_breach": int,
    "transparency_and_notice": int,
    "sensitive_children_ads_profiling": int
  },
  "rationales": {
    "lawful_basis_and_purpose": string,
    "collection_and_minimization": string,
    "secondary_use_and_limits": string,
    "retention_and_deletion": string,
    "third_parties_and_processors": string,
    "cross_border_transfers": string,
    "user_rights_and_redress": string,
    "security_and_breach": string,
    "transparency_and_notice": string,
    "sensitive_children_ads_profiling": string
  },
  "evidence": {
    "retention_and_deletion": string?,
    "user_rights_and_redress": string?,
    "security_and_breach": string?
  },
  "red_flags": string[],
  "notes": string[]
}

Scoring guidance (0–10 per category, balanced view):
- lawful_basis_and_purpose: stated purposes/bases or equivalent justification; purpose limitation; clarity of consent/choice where relevant.
- collection_and_minimization: necessity, proportionality, specificity of categories collected.
- secondary_use_and_limits: explicit limits on secondary/compatible use; avoid vague blanket purposes.
- retention_and_deletion: concrete periods or clear criteria; deletion/archiving; avoid indefinite retention without justification.
- third_parties_and_processors: processors/third parties; categories & purposes; role clarity (controller/processor/joint).
- cross_border_transfers: destination(s) and plain-language safeguards; user-facing clarity on transfers.
- user_rights_and_redress: how to exercise rights (access/rectification/erasure/restriction/portability/objection), timelines, contacts; escalation/appeal paths if relevant.
- security_and_breach: stated organizational/technical measures; breach handling language (if any); security contact/DPO info if applicable.
- transparency_and_notice: plain language; structure; change/version notices; contact details; cookie/consent pointers where relevant.
- sensitive_children_ads_profiling: handling of sensitive/special categories; children data statements/age gates; selling/sharing for ads and opt-out/limit choices; automated decision-making/profiling notices (if any).

Red flags (reduce scores where present):
- Indefinite or unspecified retention; “as long as we need” without criteria.
- Unspecified third-party sharing; selling/sharing for targeted ads without clear choice/basis.
- No actionable rights instructions or contacts.
- Contradictory or misleading statements vs. described practices.

Return only one JSON object. No extra text. Excerpt:
{chunk}
"""


def build_user_prompt(text: str, max_len: int = 6000) -> str:
    """
    Avoid str.format() because the schema contains many braces. Use a safe replace.

    Args:
        text: Text of the input.
        max_len: Length of input.

    Returns:
        Built user prompt.
    """
    chunk = text[:max_len] if text else ""
    return dedent(_USER_SCORING_JSON).replace("{chunk}", chunk)
