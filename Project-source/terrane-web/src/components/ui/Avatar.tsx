/** Avatar component — image (base64/url) with a name-initials fallback. petrol-teal palette. */

interface Props {
  src?: string | null;
  name?: string | null;
  email?: string | null;
  size?: number;
  className?: string;
}

function initials(name?: string | null, email?: string | null): string {
  const s = (name || email || "?").trim();
  if (!s) return "?";
  // For Chinese, use the first character; for English, use the first letters (up to 2)
  if (/[一-龥]/.test(s[0])) return s[0];
  const parts = s.split(/[\s@._-]+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join("") || s[0]).toUpperCase();
}

export function Avatar({ src, name, email, size = 32, className = "" }: Props) {
  const px = `${size}px`;
  if (src) {
    return <img src={src} alt="" style={{ width: px, height: px }} className={`shrink-0 rounded-full object-cover ${className}`} />;
  }
  return (
    <span style={{ width: px, height: px, fontSize: size * 0.4 }}
      className={`flex shrink-0 select-none items-center justify-center rounded-full bg-accent-soft font-medium text-accent ${className}`}>
      {initials(name, email)}
    </span>
  );
}
