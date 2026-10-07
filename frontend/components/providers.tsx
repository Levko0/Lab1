"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState } from "react"
import { AuthProvider as OidcProvider } from "react-oidc-context"

import { TooltipProvider } from "@/components/ui/tooltip"
import { authority, userManager } from "@/lib/auth"

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      {/*
       * OidcProvider is always mounted so useAuth() (which calls useOidcAuth()
       * unconditionally) is always safe. On the server, userManager is null and
       * we fall back to passing authority/client_id directly so react-oidc-context
       * creates its own UserManager for SSR — it will immediately resolve to
       * isAuthenticated: false with no network call.
       */}
      {userManager ? (
        <OidcProvider userManager={userManager}>
          <TooltipProvider>{children}</TooltipProvider>
        </OidcProvider>
      ) : (
        <OidcProvider
          authority={authority}
          client_id={process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? "unconfigured"}
          redirect_uri="/"
        >
          <TooltipProvider>{children}</TooltipProvider>
        </OidcProvider>
      )}
    </QueryClientProvider>
  )
}
