import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";

import { AuthProvider } from "@/auth/AuthContext";
import { BrandingProvider } from "@/branding/BrandingContext";
import { router } from "@/router";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrandingProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </BrandingProvider>
    </QueryClientProvider>
  );
}
