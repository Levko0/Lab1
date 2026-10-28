"use client"
import { zodResolver } from "@hookform/resolvers/zod"
import { CalendarIcon, Sparkles } from "lucide-react"
import { useEffect, useState, useTransition } from "react"
import { Controller, useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { ParticipantsInput } from "@/components/participants-input"
import { PasteAgendaSection } from "./paste-agenda-section"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Textarea } from "@/components/ui/textarea"
import { useCreateMeeting, useUpdateMeeting, useUpdateMeetingAgenda } from "@/hooks/use-meetings"
import { formatTime, parseIsoDay, toIsoDate, toIsoWithOffset } from "@/lib/datetime"
import type { Meeting, ParsedAgenda } from "@/lib/types"

const timePattern = /^([01]\d|2[0-3]):([0-5]\d)$/

const participantSchema = z.object({
  name: z.string().trim().min(1, "Required").max(120),
  email: z.string().trim().max(255).refine((v) => v === "" || z.email().safeParse(v).success, { message: "Invalid email" }).optional(),
})

const agendaItemSchema = z.object({
  topic: z.string().min(1),
  owner: z.string().nullable().optional(),
  minutes: z.number().nullable().optional()
})

const actionItemSchema = z.object({
  task: z.string().min(1),
  owner: z.string().nullable().optional(),
  due: z.string().nullable().optional()
})

const formSchema = z.object({
  name: z.string().trim().min(1, "Required").max(200),
  description: z.string().trim().max(2000).optional(),
  location: z.string().trim().max(200).optional(),
  date: z.date(),
  startTime: z.string().regex(timePattern, "Use HH:mm"),
  endTime: z.string().regex(timePattern, "Use HH:mm"),
  participants: z.array(participantSchema).max(50),
  agendaItems: z.array(agendaItemSchema).optional(),
  actionItems: z.array(actionItemSchema).optional(),
}).refine((data) => data.endTime > data.startTime, { message: "Must end after start", path: ["endTime"] })

type FormValues = z.infer<typeof formSchema>

function defaultValues(meeting?: Meeting): FormValues {
  if (!meeting) return { name: "", description: "", location: "", date: new Date(), startTime: "10:00", endTime: "11:00", participants: [{ name: "", email: "" }], agendaItems: [], actionItems: [] }
  return {
    name: meeting.name, description: meeting.description ?? "", location: meeting.location ?? "",
    date: parseIsoDay(meeting.starts_at), startTime: formatTime(meeting.starts_at), endTime: formatTime(meeting.ends_at),
    participants: meeting.participants.length > 0 ? meeting.participants.map((p) => ({ name: p.name, email: p.email ?? "" })) : [{ name: "", email: "" }],
    agendaItems: [], actionItems: []
  }
}

function BadgeSuggest({ field, suggested, dirty }: { field: string; suggested: Set<string>; dirty: Record<string, boolean> }) {
  if (suggested.has(field) && !dirty[field]) {
    return <Badge variant="secondary" className="ml-2 text-[10px] bg-primary/10 text-primary"><Sparkles className="size-3 mr-1"/> Suggested</Badge>
  }
  return null
}

export function MeetingFormDialog({ open, onOpenChange, meeting }: { open: boolean; onOpenChange: (open: boolean) => void; meeting?: Meeting }) {
  const createMeeting = useCreateMeeting()
  const updateMeeting = useUpdateMeeting()
  const updateAgenda = useUpdateMeetingAgenda()
  const [datePickerOpen, setDatePickerOpen] = useState(false)
  const isEdit = !!meeting
  const [aiSuggestion, setAiSuggestion] = useState<{ agenda: ParsedAgenda; model: string; prompt_version: string } | null>(null)
  const [suggestedFields, setSuggestedFields] = useState<Set<string>>(new Set())
  const [, startTransition] = useTransition()

  const form = useForm<FormValues>({ resolver: zodResolver(formSchema), defaultValues: defaultValues(meeting) })
  const { register, handleSubmit, control, reset, formState: { isSubmitting, dirtyFields } } = form

  useEffect(() => { 
    if (open) { 
      reset(defaultValues(meeting))
      startTransition(() => {
        setAiSuggestion(null)
        setSuggestedFields(new Set()) 
      })
    }
  }, [open, meeting, reset])

  const handleAgendaParsed = (agenda: ParsedAgenda, model: string, promptVersion: string) => {
    setAiSuggestion({ agenda, model, prompt_version: promptVersion })
    const newSuggested = new Set<string>()
    if (agenda.title) { form.setValue("name", agenda.title, { shouldDirty: false }); newSuggested.add("name") }
    if (agenda.starts_at) {
      const parsedDate = new Date(agenda.starts_at)
      form.setValue("date", parsedDate, { shouldDirty: false }); newSuggested.add("date")
      form.setValue("startTime", formatTime(agenda.starts_at), { shouldDirty: false }); newSuggested.add("startTime")
      if (agenda.duration_minutes) {
        const endDate = new Date(parsedDate.getTime() + agenda.duration_minutes * 60000)
        form.setValue("endTime", formatTime(endDate.toISOString()), { shouldDirty: false }); newSuggested.add("endTime")
      }
    }
    if (agenda.items?.length) { form.setValue("agendaItems", agenda.items, { shouldDirty: false }); newSuggested.add("agendaItems") }
    if (agenda.action_items?.length) { form.setValue("actionItems", agenda.action_items, { shouldDirty: false }); newSuggested.add("actionItems") }
    setSuggestedFields(newSuggested)
  }

  const dirtyRecord = Object.fromEntries(Object.entries(dirtyFields).map(([k, v]) => [k, !!v]))

  const onSubmit = handleSubmit(async (values) => {
    const payload = {
      name: values.name.trim(), description: values.description?.trim() || null, location: values.location?.trim() || null,
      starts_at: toIsoWithOffset(values.date, values.startTime), ends_at: toIsoWithOffset(values.date, values.endTime),
      participants: values.participants.filter(p => p.name.trim() !== "").map(p => ({ name: p.name.trim(), email: p.email?.trim() || null })),
    }
    try {
      const savedMeeting = meeting ? await updateMeeting.mutateAsync({ id: meeting.id, payload }) : await createMeeting.mutateAsync(payload)
      if (aiSuggestion && (values.agendaItems?.length || values.actionItems?.length)) {
        await updateAgenda.mutateAsync({
          id: savedMeeting.id,
          payload: {
            agenda: { items: values.agendaItems || [], action_items: values.actionItems || [] },
            ai_suggestion: { suggested: aiSuggestion.agenda, model: aiSuggestion.model, prompt_version: aiSuggestion.prompt_version }
          }
        })
      }
      toast.success(meeting ? "Meeting updated" : "Meeting created")
      onOpenChange(false)
    } catch { toast.error("Failed to save meeting.") }
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle>{isEdit ? "Edit meeting" : "New meeting"}</DialogTitle><DialogDescription>Change details or time.</DialogDescription></DialogHeader>
        {!isEdit && <PasteAgendaSection onAgendaParsed={handleAgendaParsed} />}
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2"><Label>Name <BadgeSuggest field="name" suggested={suggestedFields} dirty={dirtyRecord} /></Label><Input {...register("name")} /></div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2 sm:col-span-1"><Label>Date <BadgeSuggest field="date" suggested={suggestedFields} dirty={dirtyRecord} /></Label>
              <Controller control={control} name="date" render={({ field }) => (
                <Popover open={datePickerOpen} onOpenChange={setDatePickerOpen}><PopoverTrigger asChild><Button type="button" variant="outline" className="w-full justify-start font-normal"><CalendarIcon className="size-4 mr-2" />{toIsoDate(field.value)}</Button></PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start"><Calendar mode="single" selected={field.value} onSelect={(d) => { if (d) field.onChange(d); setDatePickerOpen(false) }} autoFocus /></PopoverContent></Popover>
              )} />
            </div>
            <div className="space-y-2"><Label>Start <BadgeSuggest field="startTime" suggested={suggestedFields} dirty={dirtyRecord} /></Label><Input type="time" step={900} {...register("startTime")} /></div>
            <div className="space-y-2"><Label>End <BadgeSuggest field="endTime" suggested={suggestedFields} dirty={dirtyRecord} /></Label><Input type="time" step={900} {...register("endTime")} /></div>
          </div>
          
          <Controller control={control} name="agendaItems" render={({ field }) => field.value?.length ? (
            <div className="space-y-2 border-l-2 pl-4 border-primary/20"><Label>Agenda Items <BadgeSuggest field="agendaItems" suggested={suggestedFields} dirty={dirtyRecord} /></Label>
              {field.value.map((it, i) => (
                <div key={i} className="flex gap-2"><Input className="h-8 text-sm" value={it.topic} onChange={e => { const n = [...field.value!]; n[i].topic = e.target.value; field.onChange(n) }} /><Input className="h-8 text-sm w-32" placeholder="Owner" value={it.owner || ""} onChange={e => { const n = [...field.value!]; n[i].owner = e.target.value; field.onChange(n) }} /><Button type="button" variant="ghost" className="h-8 px-2" onClick={() => { const n = [...field.value!]; n.splice(i, 1); field.onChange(n) }}>x</Button></div>
              ))}</div>
          ) : <></>} />

          <Controller control={control} name="actionItems" render={({ field }) => field.value?.length ? (
            <div className="space-y-2 border-l-2 pl-4 border-primary/20"><Label>Action Items <BadgeSuggest field="actionItems" suggested={suggestedFields} dirty={dirtyRecord} /></Label>
              {field.value.map((it, i) => (
                <div key={i} className="flex gap-2"><Input className="h-8 text-sm" value={it.task} onChange={e => { const n = [...field.value!]; n[i].task = e.target.value; field.onChange(n) }} /><Input className="h-8 text-sm w-32" placeholder="Owner" value={it.owner || ""} onChange={e => { const n = [...field.value!]; n[i].owner = e.target.value; field.onChange(n) }} /><Button type="button" variant="ghost" className="h-8 px-2" onClick={() => { const n = [...field.value!]; n.splice(i, 1); field.onChange(n) }}>x</Button></div>
              ))}</div>
          ) : <></>} />

          <div className="space-y-2"><Label>Description <BadgeSuggest field="description" suggested={suggestedFields} dirty={dirtyRecord} /></Label><Textarea rows={2} {...register("description")} /></div>
          <Controller control={control} name="participants" render={({ field }) => <ParticipantsInput value={field.value} onChange={field.onChange} errors={undefined} />} />
          <DialogFooter><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Saving…" : "Save"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
