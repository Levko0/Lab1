import { getAccessToken, getIdToken, userManager } from "@/lib/auth"
import type { ApiErrorBody, ApiErrorDetail, Meeting, MeetingCreateInput, MeetingList, UserProfile } from "@/lib/types"

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  readonly code: string
  readonly details: ApiErrorDetail[]
  readonly status: number

  constructor(status: number, code: string, message: string, details: ApiErrorDetail[]) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getAccessToken()
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
      cache: "no-store",
    })
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the meetings API.", [])
  }

  if (response.status === 401) {
    void userManager?.removeUser()
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null

  if (!response.ok) {
    const body = payload as ApiErrorBody | null
    throw new ApiError(
      response.status,
      body?.error?.code ?? "internal_error",
      body?.error?.message ?? `Request failed with status ${response.status}.`,
      body?.error?.details ?? [],
    )
  }

  return payload as T
}

export function listMeetings(params: { date?: string; q?: string } = {}) {
  const search = new URLSearchParams()
  if (params.date) search.set("date", params.date)
  if (params.q) search.set("q", params.q)
  const query = search.toString()
  return request<MeetingList>(`/api/v1/meetings${query ? "?" + query : ""}`)
}

export function getMeeting(id: string) {
  return request<Meeting>(`/api/v1/meetings/${id}`)
}

export function createMeeting(payload: MeetingCreateInput) {
  return request<Meeting>("/api/v1/meetings", { method: "POST", body: JSON.stringify(payload) })
}

export function updateMeeting(id: string, payload: MeetingCreateInput) {
  return request<Meeting>(`/api/v1/meetings/${id}`, { method: "PUT", body: JSON.stringify(payload) })
}

export function deleteMeeting(id: string) {
  return request<void>(`/api/v1/meetings/${id}`, { method: "DELETE" })
}

export function getMe() {
  return request<UserProfile>("/api/v1/me")
}

export async function syncMe(idToken: string): Promise<UserProfile> {
  const accessToken = await getAccessToken()
  const response = await fetch(`${API_BASE_URL}/api/v1/me/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ id_token: idToken }),
    cache: "no-store",
  })
  if (!response.ok) throw new ApiError(response.status, "sync_error", "Profile sync failed.", [])
  return response.json() as Promise<UserProfile>
}

export { getIdToken }

export interface MeetingAgendaUpdatePayload {
  agenda: { items: { topic: string; owner?: string | null; minutes?: number | null }[]; action_items: { task: string; owner?: string | null; due?: string | null }[] }
  ai_suggestion?: { suggested: unknown; model: string; prompt_version: string }
}

export function updateMeetingAgenda(id: string, payload: MeetingAgendaUpdatePayload) {
  return request<void>(`/api/v1/meetings/${id}/agenda`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}
