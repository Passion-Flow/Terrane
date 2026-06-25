/** Terrane brand mark —— stacked cards / folder shape + black "T" letter (digital-tech-app style), on a dark rounded tile.
 *  The "T" is fully centered within the white card with padding all around (never touching the black base); the mark is a black-on-white app-icon, recognizable consistently in light and dark themes.
 *  The text portion reads from the branding context (the deployer can change the product name under "Settings → Branding"). */

import { useBranding } from "@/branding/BrandingContext";

/** Factory default mark (pure SVG, independent of the branding context) —— the "current logo" when no custom logo has been uploaded. */
export function LogoMarkDefault({ size = 30, label = "Terrane" }: { size?: number; label?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={label} className="shrink-0">
      <rect width="64" height="64" rx="15" fill="#0b1012" />
      {/* Back card: stroked rounded rectangle, slightly rotated, peeking out behind (stacked look) */}
      <g transform="rotate(-6 32 32)">
        <rect x="15" y="17" width="34" height="27" rx="6" fill="none" stroke="#ffffff" strokeWidth="1.7" />
      </g>
      {/* Front card: solid white body + folder tab in the top-left */}
      <rect x="14" y="24" width="36" height="25" rx="6" fill="#ffffff" />
      <path d="M16 26 a3 3 0 0 1 3 -3 h7 a2.5 2.5 0 0 1 2.2 1.4 l1.2 2.2 h2 v3 h-17.6 z" fill="#ffffff" />
      {/* "T" letter: fully centered within the white card, padded all around */}
      <text x="32" y="42.3" textAnchor="middle" fontFamily="Geist, system-ui, sans-serif" fontSize="19" fontWeight="800" fill="#0a0a0a">T</text>
    </svg>
  );
}

export function LogoMark({ size = 30 }: { size?: number }) {
  const { logo_data, product_name } = useBranding();
  // The deployer uploaded a custom logo (data URI/URL) → use it; otherwise fall back to the factory SVG mark.
  if (logo_data) {
    return (
      <img src={logo_data} width={size} height={size} alt={product_name}
        className="shrink-0 rounded-[6px] object-contain" style={{ width: size, height: size }} />
    );
  }
  return <LogoMarkDefault size={size} label={product_name} />;
}

export function Logo() {
  const { product_name } = useBranding();
  return (
    <span className="inline-flex items-center gap-2.5 select-none">
      <LogoMark />
      <span className="text-[17px] font-semibold tracking-tight text-ink">{product_name}</span>
    </span>
  );
}
