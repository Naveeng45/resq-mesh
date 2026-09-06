"""Input guardrails for a natural-language meal-coverage query.

The LLM only extracts facts (see app/mission_agent.py), and every downstream
decision is deterministic, so a prompt-injection attack cannot directly allocate
resources. But a crafted query could still try to make the extractor emit junk or
follow embedded instructions. This module is a cheap first line of defense:

- bound the input size,
- strip control characters and collapse whitespace,
- flag known injection patterns,

and it is fully deterministic and unit-testable - no LLM call here. The demo
proceeds with the sanitized text but logs the flags, because the LLM cannot
allocate resources anyway; a stricter deployment could block on ``safe == False``.
"""

from __future__ import annotations

import re

from pydantic import ConfigDict, Field

from app.pydantic_compat import CompatBaseModel

MAX_QUERY_CHARS = 2000

# Patterns that indicate an attempt to override the extractor's instructions,
# exfiltrate the system prompt, or hijack the role. Matched case-insensitively.
# Kept deliberately narrow to limit false positives on real coordinator messages.
_INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", "instruction_override"),
    (r"disregard\s+(the\s+)?(system|previous|above)", "instruction_override"),
    (r"forget\s+(everything|all|your\s+instructions)", "instruction_override"),
    (r"you\s+are\s+now\b", "role_override"),
    (r"pretend\s+to\s+be\b", "role_override"),
    (r"system\s+prompt", "prompt_exfiltration"),
    (r"reveal\s+(your|the)\s+(prompt|instructions|system)", "prompt_exfiltration"),
    (r"print\s+(your|the)\s+(prompt|instructions)", "prompt_exfiltration"),
    (r"</?(system|assistant|user)>", "role_tag_injection"),
    (r"\bDAN\b", "jailbreak"),
    (r"developer\s+mode", "jailbreak"),
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class GuardrailResult(CompatBaseModel):
    """Outcome of screening one incident query."""

    model_config = ConfigDict(extra="forbid")

    safe: bool
    sanitized_text: str
    original_length: int
    truncated: bool = False
    flags: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def sanitize_incident_text(text: str) -> GuardrailResult:
    """Screen and normalize a free-text incident description.

    ``safe`` is False when an injection pattern is detected. Callers decide
    whether to block or to proceed with ``sanitized_text``.
    """

    original_length = len(text)
    cleaned = _CONTROL_CHARS.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    truncated = False
    if len(cleaned) > MAX_QUERY_CHARS:
        cleaned = cleaned[:MAX_QUERY_CHARS].rstrip()
        truncated = True

    flags: list[str] = []
    reasons: list[str] = []
    for pattern, label in _INJECTION_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            if label not in flags:
                flags.append(label)
                reasons.append(f"Detected possible {label.replace('_', ' ')}.")

    if truncated:
        reasons.append(f"Input truncated to {MAX_QUERY_CHARS} characters.")

    return GuardrailResult(
        safe=not flags,
        sanitized_text=cleaned,
        original_length=original_length,
        truncated=truncated,
        flags=flags,
        reasons=reasons,
    )
