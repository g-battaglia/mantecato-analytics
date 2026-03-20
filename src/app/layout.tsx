import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Mantecato",
  description: "Power analytics for Umami",
};

function resolveThemeClass(theme: string | undefined): "light" | "dark" {
  if (theme === "light") return "light";
  if (theme === "dark") return "dark";
  return "dark";
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const themeCookie = cookieStore.get("theme")?.value as
    | "light"
    | "dark"
    | "system"
    | undefined;
  const themeClass = resolveThemeClass(themeCookie);
  const initialTheme = themeCookie ?? "dark";

  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} ${themeClass}`}
      suppressHydrationWarning
    >
      <body className="min-h-svh bg-background text-foreground antialiased">
        <Providers initialTheme={initialTheme}>{children}</Providers>
      </body>
    </html>
  );
}
