import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "accent" | "success" | "attention" | "surface";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-primary text-white",
  accent: "bg-accent text-white",
  success: "bg-success text-white",
  attention: "bg-attention text-white",
  surface: "bg-surface text-text border-2 border-primary"
};

interface BigButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
  children: ReactNode;
}

/** One action per screen is the rule — this is the one button shape used
 * everywhere a patient taps something. Never shrink below min-h-touch. */
export function BigButton({ variant = "primary", icon, children, className = "", ...rest }: BigButtonProps) {
  return (
    <button
      type="button"
      className={`flex min-h-touch w-full items-center justify-center gap-3 rounded-token px-6 text-base font-semibold shadow-sm transition-transform active:scale-[0.98] motion-reduce:transition-none disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}
