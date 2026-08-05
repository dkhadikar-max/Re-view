import { cn, statusTone } from "@/lib/utils";

export function Badge({
  children,
  tone,
  className,
}: {
  children: React.ReactNode;
  tone?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize",
        tone ? statusTone(tone) : "bg-ink-100 text-ink-600",
        className
      )}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  hint,
  accent,
  delay = 0,
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: "sea" | "sand" | "coral" | "ink";
  delay?: number;
}) {
  const accents = {
    sea: "from-sea-500/10 to-transparent",
    sand: "from-sand-300/30 to-transparent",
    coral: "from-coral-500/10 to-transparent",
    ink: "from-ink-200/40 to-transparent",
  };
  return (
    <div
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "animate-fade-up opacity-0 relative overflow-hidden rounded-2xl border border-ink-200/60 bg-white/60 p-5 backdrop-blur"
      )}
    >
      <div
        className={cn(
          "pointer-events-none absolute inset-0 bg-gradient-to-br",
          accents[accent || "ink"]
        )}
      />
      <p className="relative text-xs font-medium uppercase tracking-wider text-ink-500">
        {label}
      </p>
      <p className="relative mt-2 font-display text-3xl text-ink-950">{value}</p>
      {hint && <p className="relative mt-1 text-xs text-ink-400">{hint}</p>}
    </div>
  );
}

export function Panel({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "animate-fade-up rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur opacity-0",
        className
      )}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-display text-xl text-ink-900">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="py-8 text-center text-sm text-ink-400">{children}</p>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const variants = {
    primary:
      "bg-sea-600 text-white hover:bg-sea-700 shadow-sm shadow-sea-600/20",
    secondary:
      "border border-ink-200 bg-white text-ink-800 hover:border-sea-400",
    danger: "bg-coral-500 text-white hover:bg-coral-600",
    ghost: "text-ink-600 hover:bg-ink-100",
  };
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:opacity-50",
        variants[variant],
        className
      )}
    >
      {children}
    </button>
  );
}
