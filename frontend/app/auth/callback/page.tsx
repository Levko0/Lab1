"use client"

import { useEffect } from "react"
import { useAuth } from "react-oidc-context"
import { useRouter } from "next/navigation"

import { AuthLoading } from "@/components/require-auth"

/**
 * /auth/callback/ — OIDC redirect_uri.
 *
 * Cognito (and Google via Cognito) redirects here with ?code=... after the
 * user signs in. signinCallback() exchanges the code for tokens and stores
 * them; then we navigate to the app.
 *
 * If there is no ?code in the URL (e.g. after a Cognito logout that redirects
 * here) we simply send the user back to /login/.
 */
export default function CallbackPage() {
  const auth = useAuth()
  const router = useRouter()

  useEffect(() => {
    // Still initialising — wait.
    if (auth.isLoading) return

    // The library already handled the callback (hasCodeInUrl was true on mount)
    // and the user is now authenticated.
    if (auth.isAuthenticated) {
      router.replace("/today/")
      return
    }

    // No code in the URL (e.g. post-logout redirect here): go to login.
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search)
      if (!params.has("code") && !params.has("error")) {
        router.replace("/login/")
      }
    }
  }, [auth.isLoading, auth.isAuthenticated, router])

  // Show an error returned by Cognito (e.g. access_denied from Google).
  if (auth.error) {
    return (
      <div className="flex flex-1 items-center justify-center py-24">
        <p className="text-sm text-destructive">
          Sign-in failed: {auth.error.message}
        </p>
      </div>
    )
  }

  return <AuthLoading label="Completing sign in…" />
}
