"use client"
import { Sparkles, X } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { parseAgendaText } from "@/lib/parser"
import type { ParsedAgenda } from "@/lib/types"

export function PasteAgendaSection({ onAgendaParsed }: { onAgendaParsed: (agenda: ParsedAgenda, model: string, pv: string) => void }) {
  const [text, setText] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const handleParse = async () => {
    if (!text.trim()) return
    const controller = new AbortController()
    abortRef.current = controller
    setIsLoading(true)
    try {
      const res = await parseAgendaText({ text: text.trim(), signal: controller.signal })
      toast.success("Agenda parsed")
      onAgendaParsed(res.agenda, res.model, res.prompt_version)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error"
      if (msg !== "Cancelled") toast.error(msg)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Card className="border-dashed bg-muted/20">
      <CardHeader className="pb-3"><CardTitle className="text-base flex items-center gap-2"><Sparkles className="size-4" /> Paste an Agenda</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <Textarea placeholder="Paste meeting notes..." value={text} onChange={(e) => setText(e.target.value)} disabled={isLoading} className="text-sm" />
        <div className="flex justify-between">
          <span className="text-xs text-muted-foreground">{text.length} / 10,000 characters</span>
          <div className="flex gap-2">
            {isLoading ? (
              <Button variant="outline" size="sm" onClick={() => abortRef.current?.abort()}><X className="size-3 mr-1" /> Cancel</Button>
            ) : (
              <Button size="sm" onClick={handleParse} disabled={!text.trim()}><Sparkles className="size-3 mr-1" /> Parse</Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
