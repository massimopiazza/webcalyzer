import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      theme="dark"
      toastOptions={{
        classNames: {
          toast:
            "border border-border bg-card text-card-foreground shadow-lg backdrop-blur",
        },
      }}
    />
  );
}
