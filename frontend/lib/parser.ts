import { getIdToken } from "@/lib/auth"
import type { ParsedAgenda } from "@/lib/types"

export const PARSER_URL = process.env.NEXT_PUBLIC_PARSER_URL ?? ""

export class AgendaParseError extends Error {
  constructor(message: string, public status?: number) {
    super(message)
    this.name = "AgendaParseError"
  }
}

export async function parseAgendaText({ text, signal }: { text: string; signal?: AbortSignal }) {
  if (text.length > 10000) throw new AgendaParseError("Text is too long", 413)

  const idToken = await getIdToken()
  const today = new Date().toISOString().split("T")[0]
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  const url = PARSER_URL || "http://localhost:8000/api/v1/ai/parse-agenda"

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(idToken ? { Authorization: `Bearer ${idToken}` } : {}),
      },
      body: JSON.stringify({ text, today, tz }),
      signal,
    })

    if (!res.ok) {
      if (res.status === 413) throw new AgendaParseError("Text is too long", 413)
      if (res.status === 429) throw new AgendaParseError("Service busy", 429)
      const data = (await res.json().catch(() => ({}))) as { error?: string }
      throw new AgendaParseError(data.error || "Parsing failed", res.status)
    }
    return (await res.json()) as { agenda: ParsedAgenda; model: string; prompt_version: string }
  } catch (err: unknown) {
    if (err instanceof AgendaParseError) throw err
    if (err instanceof Error && err.name === "AbortError") throw new AgendaParseError("Cancelled")
    throw new AgendaParseError("Network error")
  }
}
