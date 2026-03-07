import { cn } from "@/lib/utils"

interface PriorityBadgeProps {
  priority: number
  className?: string
}

const priorityClasses: Record<number, string> = {
  1: 'text-red-400',
  2: 'text-yellow-400',
  3: 'text-gray-400',
  4: 'text-gray-500',
  5: 'text-gray-600',
}

export function PriorityBadge({ priority, className }: PriorityBadgeProps) {
  const colorClass = priorityClasses[priority] || priorityClasses[3]

  return (
    <span
      className={cn(
        'font-mono text-sm font-semibold',
        colorClass,
        className
      )}
    >
      P{priority}
    </span>
  )
}
