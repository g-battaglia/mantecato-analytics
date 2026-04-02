import { useState } from "react";
import { useNavigate } from "react-router";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Moon, Sun, LogOut, Share2, Check } from "lucide-react";
import { useTheme } from "@/lib/theme";

export function Header({
  title,
  shareId,
}: {
  title?: string;
  shareId?: string | null;
}) {
  const navigate = useNavigate();
  const { resolvedTheme, setTheme } = useTheme();
  const [copied, setCopied] = useState(false);

  async function handleLogout() {
    await fetch("/api/auth", { method: "DELETE" });
    navigate("/login");
  }

  function handleCopyShareLink() {
    if (!shareId) return;
    const url = `${window.location.origin}/share/${shareId}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <header className="sticky top-0 z-10 flex h-[60px] shrink-0 items-center gap-4 border-b bg-background px-6">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-6!" />
      {title && (
        <h1 className="text-sm font-semibold">{title}</h1>
      )}
      <div className="ml-auto flex items-center gap-2">
        {shareId && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleCopyShareLink}
            title="Copy public share link"
          >
            {copied ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Share2 className="h-4 w-4" />
            )}
            <span className="sr-only">Copy share link</span>
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>
        <Button variant="ghost" size="icon-sm" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
          <span className="sr-only">Sign out</span>
        </Button>
      </div>
    </header>
  );
}
