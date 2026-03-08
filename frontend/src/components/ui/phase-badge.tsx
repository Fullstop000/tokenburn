import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

type Phase =
  | 'cycle'
  | 'discover'
  | 'value'
  | 'plan'
  | 'execute'
  | 'verify'
  | 'git'
  | 'decision'
  | 'system'
  | 'discovery'
  | 'execution'
  | 'memory'
  | 'inbox'
  | 'llm'
  | 'controlplane'

const phaseVariants: Record<Phase, string> = {
  cycle: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  discover: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  value: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  plan: 'bg-gray-500/10 text-gray-300 border-gray-500/20',
  execute: 'bg-green-500/10 text-green-400 border-green-500/20',
  verify: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  git: 'bg-red-500/10 text-red-400 border-red-500/20',
  decision: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  system: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  discovery: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  execution: 'bg-green-500/10 text-green-400 border-green-500/20',
  memory: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  inbox: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  llm: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  controlplane: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
}

interface PhaseBadgeProps {
  phase: string
  label?: string
  className?: string
}

export function PhaseBadge({ phase, label, className }: PhaseBadgeProps) {
  const variantClass = phaseVariants[phase as Phase] || phaseVariants.system

  return (
    <Badge
      variant="outline"
      className={cn(
        'font-mono text-xs font-medium',
        variantClass,
        className
      )}
    >
      {label ?? phase}
    </Badge>
  )
}
