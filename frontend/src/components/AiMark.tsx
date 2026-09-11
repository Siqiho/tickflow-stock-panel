import mark from '@/assets/ai-mark.png'

interface AiMarkProps {
  className?: string
  size?: number
}

/** Stored AI entry artwork from the selected session, not a redraw. */
export function AiMark({ className, size = 64 }: AiMarkProps) {
  return (
    <img
      src={mark}
      width={size}
      height={size}
      alt=""
      draggable={false}
      className={className}
    />
  )
}
