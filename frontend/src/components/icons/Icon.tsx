import type { ComponentType, SVGProps } from "react";

/**
 * Central wrapper for Hero Icons. The app uses outline icons for ordinary
 * actions; individual views may opt into the matching solid component for
 * an active or critical state.
 */
export function Icon({
  icon,
  size = 20,
  className = "",
}: {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  size?: number;
  className?: string;
}) {
  const HeroIcon = icon;
  return <HeroIcon width={size} height={size} className={className} aria-hidden="true" />;
}
