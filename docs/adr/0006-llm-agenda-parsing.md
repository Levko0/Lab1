# 6. LLM-Assisted Agenda Parsing

* Status: Accepted
* Deciders: Levko Zhuraiev
* Date: 2026-10-27

## Context and Problem Statement
Users paste unstructured agendas (emails, chats). We need to parse them into structured forms, keeping costs low and preventing prompt injection from affecting the system.

## Decision Drivers
* Cost: No NAT Gateway or VPC endpoint overhead when idle.
* Security: Pasted text is untrusted. Model must not have write access.

## Considered Options
1. **Claude Haiku 4.5 via Bedrock in Lambda outside VPC (Chosen)**
2. **Bedrock via VPC Interface Endpoint:** Costs ~$7.30/month even when idle.
3. **Claude API directly:** Requires external API keys.
4. **Regex/heuristics:** Too fragile for natural language.
5. **Claude Opus 5.5 / Mantle API:** Used Haiku 4.5 due to account limits.

## Decision Outcome
Chosen Option 1. The LLM parsing runs in a public-facing Lambda URL outside the VPC, validating the Cognito JWT token. It only returns JSON suggestions. Writing the agenda happens via the existing API inside the VPC.

## Consequences
* **Positive:** $0 idle cost. Immune to data-altering prompt injections since the model only suggests and has no DB access.
* **Negative:** Requires JWT verification outside the main API.
* **Resilience:** If Bedrock is throttled or down, manual entry still works seamlessly.
