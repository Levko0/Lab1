"use client"

/**
 * Auth adapter layer: wraps react-oidc-context's useAuth() in the shape the
 * rest of the app expects (status, user, signOut).
 *
 * Must be called inside <OidcProvider> (see components/providers.tsx).
 * The OidcProvider is always mounted — even when auth isn't configured — so
 * this hook is always safe to call unconditionally.
 */

import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef } from "react"
import { useAuth as useOidcAuth } from "react-oidc-context"

import { syncMe } from "@/lib/api"
import { cognitoLogoutUrl, userManager } from "@/lib/auth"

export type AuthUser = {
  sub: string
  email?: string
  name?: string
}

export type AuthContextValue =
  | { status: "loading"; user: null; signOut: () => Promise<void> }
  | { status: "signedOut"; user: null; signOut: () => Promise<void> }
  | { status: "signedIn"; user: AuthUser; signOut: () => Promise<void> }

/**
 * Drop-in replacement for the old useAuth(). Reads from react-oidc-context and
 * exposes a stable {status, user, signOut} shape to the rest of the app.
 */
export function useAuth(): AuthContextValue {
  const oidc = useOidcAuth()
  const queryClient = useQueryClient()
  const syncedSub = useRef<string | null>(null)
  const prevSub = useRef<string | null>(null)

  // Derive a stable AuthUser from the OIDC profile.
  const currentSub = oidc.user?.profile.sub ?? null
  const user: AuthUser | null = oidc.user
    ? {
        sub: oidc.user.profile.sub,
        email:
          typeof oidc.user.profile.email === "string"
            ? oidc.user.profile.email
            : undefined,
        name:
          typeof oidc.user.profile.name === "string"
            ? oidc.user.profile.name
            : undefined,
      }
    : null

  // After sign-in, sync the profile to the backend exactly once per sub.
  useEffect(() => {
    if (!oidc.user || syncedSub.current === currentSub) return
    syncedSub.current = currentSub
    const idToken = oidc.user.id_token
    if (idToken) {
      syncMe(idToken).catch((err) => console.warn("Profile sync failed", err))
    }
  }, [oidc.user, currentSub])

  // Clear RQ cache when the signed-in account changes.
  useEffect(() => {
    if (prevSub.current !== null && prevSub.current !== currentSub) {
      queryClient.clear()
    }
    prevSub.current = currentSub
  }, [currentSub, queryClient])

  const signOut = useCallback(async () => {
    // 1. Remove the local OIDC session from localStorage.
    await userManager.removeUser()
    // 2. Clear cached API data so another user's data never leaks.
    queryClient.clear()
    // 3. Redirect to Cognito's /logout endpoint to clear the server session.
    if (typeof window !== "undefined") {
      window.location.href = cognitoLogoutUrl(window.location.origin)
    }
  }, [queryClient])

  if (oidc.isLoading) return { status: "loading", user: null, signOut }
  if (oidc.isAuthenticated && user) return { status: "signedIn", user, signOut }
  return { status: "signedOut", user: null, signOut }
}
