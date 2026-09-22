"use client";

import React, { useState } from "react";
import { Popover } from "@opal/components";

export interface SimplePopoverProps extends React.ComponentPropsWithoutRef<
  typeof Popover.Content
> {
  onOpenChange?: (open: boolean) => void;
  trigger: React.ReactNode | ((open: boolean) => React.ReactNode);
}

export default function SimplePopover({
  trigger,
  onOpenChange,
  ...rest
}: SimplePopoverProps) {
  const [open, setOpen] = useState(false);

  function handleOnOpenChange(state: boolean) {
    setOpen(state);
    onOpenChange?.(state);
  }

  return (
    <Popover open={open} onOpenChange={handleOnOpenChange}>
      <Popover.Trigger asChild>
        <div>{typeof trigger === "function" ? trigger(open) : trigger}</div>
      </Popover.Trigger>
      {/* "fit" (Opal's own default) sizes the box to its content; the previous
          "md" (w-48 = 192px) clipped any panel wider than that, cutting off
          the credits and grid-status popovers. Callers still override via rest. */}
      <Popover.Content align="start" side="top" width="fit" {...rest} />
    </Popover>
  );
}
