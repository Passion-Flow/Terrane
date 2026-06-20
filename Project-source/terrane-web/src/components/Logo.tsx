/** Terrane 品牌标识 —— 堆叠卡片 / 文件夹造型 + 黑色 T 字（digital-tech-app 风），深色圆角磗承载。
 *  T 字完整居中在白卡内、四周留白（不触黑底）；标记黑底白形 app-icon，浅暗主题一致辨识。
 *  文字/图标走品牌上下文（部署方可在后台「设置→品牌外观」改产品名 + 上传 Logo）。 */

import { useBranding } from "@/branding/BrandingContext";

export function LogoMark({ size = 30 }: { size?: number }) {
  const { logo_data, product_name } = useBranding();
  if (logo_data) {
    return (
      <img src={logo_data} width={size} height={size} alt={product_name}
        className="shrink-0 rounded-[6px] object-contain" style={{ width: size, height: size }} />
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={product_name} className="shrink-0">
      <rect width="64" height="64" rx="15" fill="#0b1012" />
      {/* 后卡：描边圆角矩形，轻微旋转，露在后方（堆叠感） */}
      <g transform="rotate(-6 32 32)">
        <rect x="15" y="17" width="34" height="27" rx="6" fill="none" stroke="#ffffff" strokeWidth="1.7" />
      </g>
      {/* 前卡：实白 主体 + 左上文件夹凸标 */}
      <rect x="14" y="24" width="36" height="25" rx="6" fill="#ffffff" />
      <path d="M16 26 a3 3 0 0 1 3 -3 h7 a2.5 2.5 0 0 1 2.2 1.4 l1.2 2.2 h2 v3 h-17.6 z" fill="#ffffff" />
      {/* T 字：完整居中白卡内，四周留白 */}
      <text x="32" y="42.3" textAnchor="middle" fontFamily="Geist, system-ui, sans-serif" fontSize="19" fontWeight="800" fill="#0a0a0a">T</text>
    </svg>
  );
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
