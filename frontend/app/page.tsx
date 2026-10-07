"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"

/**
 * Root page: immediately redirects to the login entry-point.
 * Client-side replace() so the static export doesn't need a server redirect.
 */
export default function Home() {
  const router = useRouter()
  useEffect(() => {
    router.replace("/login/")
  }, [router])
  return null
}
