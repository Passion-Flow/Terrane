/** 品牌上下文 —— 启动即拉公开 branding，全局提供产品名 / 主题色 / 登录副标题。
 *  副作用：产品名写入 document.title；主题色覆写 --color-accent 三件套 CSS 变量。
 *  缺省回退出厂值（页面化零配置），失败不阻塞渲染。设置页保存后 invalidate ["branding"] 即刷新。 */

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { DEFAULT_BRANDING, getBranding, type Branding } from "@/lib/branding";

const BrandingContext = createContext<Branding>(DEFAULT_BRANDING);

export function useBranding(): Branding {
  return useContext(BrandingContext);
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: getBranding,
    staleTime: 5 * 60_000,
  });
  const branding = data ?? DEFAULT_BRANDING;

  // 产品名 → 标签页标题（保留「管理后台」后缀）。
  useEffect(() => {
    document.title = `${branding.product_name} 管理后台`;
  }, [branding.product_name]);

  // favicon：专用 favicon 优先，缺省回退控制台 Logo，再缺省保留出厂 favicon.svg。
  useEffect(() => {
    const icon = branding.favicon ?? branding.logo_data;
    if (!icon) return;
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
      ?? document.head.appendChild(Object.assign(document.createElement("link"), { rel: "icon" }));
    const prev = link.getAttribute("href");
    link.setAttribute("href", icon);
    link.removeAttribute("type");  // data URI 自带 MIME，去掉固定 image/svg+xml
    return () => { if (prev) link.setAttribute("href", prev); };
  }, [branding.favicon, branding.logo_data]);

  // 主题色 → 覆写 accent CSS 变量（hex 优先；hover/soft 跟随同色保证一致观感）。
  useEffect(() => {
    const root = document.documentElement;
    const c = branding.accent_color;
    if (c && c !== DEFAULT_BRANDING.accent_color) {
      root.style.setProperty("--color-accent", c);
      root.style.setProperty("--color-accent-hover", c);
    } else {
      root.style.removeProperty("--color-accent");
      root.style.removeProperty("--color-accent-hover");
    }
  }, [branding.accent_color]);

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>;
}
