import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

type TaskStatus =
  | 'queued'
  | 'planning'
  | 'running'
  | 'executing'
  | 'completed'
  | 'needs_human'
  | 'human_resolved'
  | 'failed'
  | 'cancelled'
  | 'discovered'

const statusVariants: Record<TaskStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; className: string }> = {
  queued: { variant: 'secondary', className: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  planning: { variant: 'secondary', className: 'bg-purple-500/10 text-purple-400 border-purple-500/20' },
  running: { variant: 'secondary', className: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' },
  executing: { variant: 'secondary', className: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' },
  completed: { variant: 'default', className: 'bg-green-500/10 text-green-400 border-green-500/20' },
  needs_human: { variant: 'secondary', className: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20 animate-pulse' },
  human_resolved: { variant: 'secondary', className: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' },
  failed: { variant: 'destructive', className: 'bg-red-500/10 text-red-400 border-red-500/20' },
  cancelled: { variant: 'outline', className: 'bg-gray-500/10 text-gray-400 border-gray-500/20' },
  discovered: { variant: 'outline', className: 'bg-gray-500/10 text-gray-400 border-gray-500/20' },
}

interface StatusBadgeProps {
  status: string
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusVariants[status as TaskStatus] || statusVariants.cancelled

  return (
    <Badge
      variant={config.variant}
      className={cn(
        'font-medium capitalize',
        config.className,
        className
      )}
    >
      <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-current" />
      {status.replace(/_/g, ' ')}
    </Badge>
  )
}
