import { UserManager, WebStorageStateStore } from "oidc-client-ts"

const userPoolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? ""
const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? ""
// e.g. <prefix>.auth.us-east-1.amazoncognito.com
const cognitoDomain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN ?? ""

export const isAuthConfigured = Boolean(userPoolId && clientId)

/**
 * OIDC authority: the Cognito user pool issuer URL.
 * Discovery document is at <authority>/.well-known/openid-configuration.
 */
export const authority = userPoolId
  ? `https://cognito-idp.us-east-1.amazonaws.com/${userPoolId}`
  : "https://cognito-idp.us-east-1.amazonaws.com/unconfigured"

/**
 * The hosted-UI domain used to build the logout URL.
 * Present only when NEXT_PUBLIC_COGNITO_DOMAIN is set.
 */
export const hostedDomain = cognitoDomain

/**
 * Shared UserManager instance.
 * Browser-only: on the server (SSG/SSR) this is a stub that is never called.
 * When auth is not configured the manager is still created but will never
 * successfully authenticate (authority points nowhere real).
 */
export const userManager: UserManager =
  typeof window !== "undefined"
    ? new UserManager({
        authority,
        client_id: clientId || "unconfigured",
        redirect_uri: `${window.location.origin}/auth/callback/`,
        post_logout_redirect_uri: `${window.location.origin}/auth/callback/`,
        scope: "openid email profile",
        response_type: "code",
        userStore: new WebStorageStateStore({ store: window.localStorage }),
        // Cognito does not expose end_session_endpoint in its discovery doc,
        // so we build the logout URL manually in cognitoLogoutUrl().
        revokeTokensOnSignout: false,
      })
    : // SSR stub: never called, satisfies the type.
      (null as unknown as UserManager)

/** Returns the current access token, or null when nobody is signed in. */
export async function getAccessToken(): Promise<string | null> {
  if (!isAuthConfigured || typeof window === "undefined" || !userManager) return null
  try {
    const user = await userManager.getUser()
    if (!user || user.expired) return null
    return user.access_token ?? null
  } catch {
    return null
  }
}

/** Returns the current ID token, or null when nobody is signed in. */
export async function getIdToken(): Promise<string | null> {
  if (!isAuthConfigured || typeof window === "undefined" || !userManager) return null
  try {
    const user = await userManager.getUser()
    if (!user || user.expired) return null
    return user.id_token ?? null
  } catch {
    return null
  }
}

/**
 * Builds the Cognito-hosted logout URL.
 * Cognito does not publish end_session_endpoint, so we construct it manually.
 */
export function cognitoLogoutUrl(origin: string): string {
  return (
    `https://${cognitoDomain}/logout` +
    `?client_id=${encodeURIComponent(clientId)}` +
    `&logout_uri=${encodeURIComponent(`${origin}/auth/callback/`)}`
  )
}
