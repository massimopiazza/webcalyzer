import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
  {
    variants: {
      variant: {
        default: "bg-primary/10 text-primary border-primary/40",
        secondary: "bg-secondary text-secondary-foreground border-transparent",
        outline: "border-border text-muted-foreground",
        success: "bg-success/15 text-success border-success/40",
        warning: "bg-warning/15 text-warning border-warning/40",
        destructive: "bg-destructive/15 text-destructive border-destructive/40",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
