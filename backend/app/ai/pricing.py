"""Token pricing calculation for LLM calls."""

from typing import Any

# Haiku 4.5 list prices in USD per 1,000,000 tokens
# Prices to verify against AWS Bedrock pricing:
HAIKU_4_5_INPUT_PER_MILLION: float = 1.00  # Price to verify: $1.00 / 1M input tokens
HAIKU_4_5_OUTPUT_PER_MILLION: float = 5.00  # Price to verify: $5.00 / 1M output tokens


def cost_usd(model: str, usage: Any) -> float:
    """Calculate the USD cost for a model call given its token usage.

    Returns 0.0 for unknown models. Prices are constants to verify before production billing.
    """
    if "haiku-4-5" not in model:
        return 0.0

    input_rate = HAIKU_4_5_INPUT_PER_MILLION
    output_rate = HAIKU_4_5_OUTPUT_PER_MILLION

    if hasattr(usage, "input_tokens"):
        input_tokens = usage.input_tokens or 0
    elif isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", 0) or 0
    else:
        input_tokens = 0

    if hasattr(usage, "output_tokens"):
        output_tokens = usage.output_tokens or 0
    elif isinstance(usage, dict):
        output_tokens = usage.get("output_tokens", 0) or 0
    else:
        output_tokens = 0

    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000.0
