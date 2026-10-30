import type { Metadata } from "next";
import { DM_Sans, Space_Grotesk } from "next/font/google";
import { ThemeProvider } from "../components/theme-provider";
import { AmbientBackdrop } from "../components/visual/ambient-backdrop";
import { themeInitScript } from "../lib/theme";
import "./globals.css";
import "./ui.css";
import "./visual.css";

const sans = DM_Sans({ subsets: ["latin"], variable: "--font-sans" });
const display = Space_Grotesk({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "TritonSpend AI",
  description: "Make your Dining Dollars last with a clear, deterministic forecast."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint to avoid a flash of the default theme. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className={`${sans.variable} ${display.variable}`}>
        <AmbientBackdrop />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
