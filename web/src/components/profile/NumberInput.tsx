import * as React from "react";
import { Input } from "@/components/ui/input";

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> & {
  value: number | null;
  onChange: (next: number | null) => void;
  allowNull?: boolean;
  step?: number | string;
  min?: number;
  max?: number;
  invalid?: boolean;
};

export function NumberInput({ value, onChange, allowNull, invalid, className, ...props }: Props) {
  const [text, setText] = React.useState<string>(value === null ? "" : String(value));

  React.useEffect(() => {
    setText(value === null ? "" : String(value));
  }, [value]);

  return (
    <Input
      type="text"
      inputMode="decimal"
      value={text}
      onChange={(e) => {
        const next = e.target.value;
        setText(next);
        if (next.trim() === "") {
          if (allowNull) onChange(null);
          return;
        }
        const parsed = Number(next);
        if (!Number.isNaN(parsed)) onChange(parsed);
      }}
      onBlur={() => {
        if (text.trim() === "") return;
        const parsed = Number(text);
        if (Number.isNaN(parsed)) {
          setText(value === null ? "" : String(value));
        }
      }}
      className={invalid ? `border-destructive ${className || ""}` : className}
      {...props}
    />
  );
}
