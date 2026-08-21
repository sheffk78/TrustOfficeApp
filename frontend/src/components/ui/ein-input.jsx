import * as React from "react"

import { cn } from "@/lib/utils"
import { formatEIN, rawEIN } from "@/utils/formatters"

const EINInput = React.forwardRef(({ className, value, onChange, placeholder, disabled, ...props }, ref) => {
  const handleChange = (e) => {
    const raw = rawEIN(e.target.value)
    const formatted = formatEIN(raw)
    if (onChange) {
      // Pass a synthetic event-like object with the formatted value
      onChange({ ...e, target: { ...e.target, value: formatted, rawValue: raw } })
    }
  }

  return (
    <input
      ref={ref}
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      maxLength={10}
      value={value}
      onChange={handleChange}
      placeholder={placeholder || "XX-XXXXXXX"}
      disabled={disabled}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      {...props}
    />
  )
})
EINInput.displayName = "EINInput"

export { EINInput }