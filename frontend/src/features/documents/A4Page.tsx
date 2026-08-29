export function A4Page({
  marginTopMm,
  marginBottomMm,
  marginLeftMm,
  marginRightMm,
  orientation = "portrait",
  className = "",
  style,
  children,
}: {
  marginTopMm: number;
  marginBottomMm: number;
  marginLeftMm: number;
  marginRightMm: number;
  orientation?: "portrait" | "landscape";
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  const isLandscape = orientation === "landscape";

  return (
    <div
      className={`mx-auto mb-6 bg-white shadow-sm ring-1 ring-[var(--color-border)] ${className}`}
      style={{
        width: isLandscape ? "297mm" : "210mm",
        minHeight: isLandscape ? "210mm" : "297mm",
        paddingTop: `${marginTopMm}mm`,
        paddingBottom: `${marginBottomMm}mm`,
        paddingLeft: `${marginLeftMm}mm`,
        paddingRight: `${marginRightMm}mm`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
