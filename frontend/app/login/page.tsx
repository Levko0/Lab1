"use client"

import { useEffect } from "react"
import { useAuth } from "react-oidc-context"
import { useRouter } from "next/navigation"

import { AuthLoading } from "@/components/require-auth"
import { isAuthConfigured } from "@/lib/auth"

/**
 * /login/ — the app's sign-in entry-point.
 *
 * If the user is already authenticated we skip straight to /today/.
 * Otherwise we immediately trigger the OIDC redirect to Cognito managed login.
 * When auth is not configured at all (no pool ID/client ID in env) we show a
 * helpful message instead of redirecting to an invalid URL.
 */
export default function LoginPage() {
  const auth = useAuth()
  const router = useRouter()

  useEffect(() => {
    // Wait until the OIDC library has finished loading the stored session.
    if (auth.isLoading) return

    if (auth.isAuthenticated) {
      router.replace("/today/")
      return
    }

    if (!isAuthConfigured) return // banner below handles this

    // Kick off the PKCE/code redirect to Cognito managed login.
    void auth.signinRedirect()
  }, [auth, router])

  if (!isAuthConfigured) {
    return (
      <div className="flex flex-1 items-center justify-center py-24 text-sm text-muted-foreground">
        Sign-in is not configured. Run{" "}
        <code className="mx-1 rounded bg-muted px-1 py-0.5">make aws-deploy-auth</code>{" "}
        and add the values from{" "}
        <code className="mx-1 rounded bg-muted px-1 py-0.5">make aws-auth-env</code>{" "}
        to your <code className="mx-1 rounded bg-muted px-1 py-0.5">.env</code>.
      </div>
    )
  }

  return <AuthLoading label="Redirecting to sign in…" />
}
