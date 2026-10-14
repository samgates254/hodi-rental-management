import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const kesFormatter = new Intl.NumberFormat("en-KE", {
  style: "currency",
  currency: "KES",
});

type CurrencyTextProps = Omit<HTMLAttributes<HTMLSpanElement>, "children"> & {
  amount: number;
};

export function CurrencyText({ amount, className, ...props }: CurrencyTextProps) {
  return (
    <span className={cn("tabular-nums", className)} {...props}>
      {kesFormatter.format(amount)}
    </span>
  );
}