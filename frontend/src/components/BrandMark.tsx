import { useTranslation } from "react-i18next";

type BrandMarkProps = {
  compact?: boolean;
  inverse?: boolean;
  showPrinciple?: boolean;
  className?: string;
};

/**
 * The PracticeFlow mark is intentionally drawn in the product codebase: it
 * stays sharp at every density and does not depend on an external brand asset.
 * The paired P/F strokes also read as two adjacent document columns.
 */
export function BrandMark({
  compact = false,
  inverse = false,
  showPrinciple = false,
  className = "",
}: BrandMarkProps) {
  const { t } = useTranslation("common");

  return (
    <div className={`inline-flex min-w-0 items-center gap-3 ${className}`}>
      <svg
        viewBox="0 0 40 40"
        role="img"
        aria-label={t("brandSymbolLabel")}
        className="size-10 shrink-0"
      >
        <rect width="40" height="40" rx="8" fill="var(--color-brand-700)" />
        <path
          d="M10.5 29.5v-19h6.2c4.2 0 6.7 2.15 6.7 5.65 0 3.55-2.5 5.85-6.7 5.85h-6.2m0-6.1h6c1.55 0 2.45-.62 2.45-1.75 0-1.1-.9-1.7-2.45-1.7h-6"
          fill="none"
          stroke="#fff"
          strokeWidth="2.2"
          strokeLinecap="square"
          strokeLinejoin="miter"
        />
        <path
          d="M25.7 29.5v-19h7.2m-7.2 8.2h5.6"
          fill="none"
          stroke="#c8d1ef"
          strokeWidth="2.2"
          strokeLinecap="square"
        />
      </svg>
      {!compact && (
        <span className="min-w-0">
          <span className={`block truncate text-[17px] font-bold tracking-[-0.025em] ${inverse ? "text-white" : "text-[var(--color-ink)]"}`}>
            PracticeFlow
          </span>
          {showPrinciple && (
            <span className={`mt-0.5 block truncate text-[11px] font-medium tracking-[0.025em] ${inverse ? "text-white/70" : "text-[var(--color-muted)]"}`}>
              {t("brandPrinciple")}
            </span>
          )}
        </span>
      )}
    </div>
  );
}
