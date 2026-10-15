"use client";

import { cn } from "@/lib/cn";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type DialogKind = "alert" | "confirm";

type DialogRequest = {
  kind: DialogKind;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  resolve: (ok: boolean) => void;
};

type ConfirmOptions = {
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type AlertOptions = {
  title?: string;
  confirmLabel?: string;
};

type AppDialogApi = {
  confirm: (message: string, options?: ConfirmOptions) => Promise<boolean>;
  alert: (message: string, options?: AlertOptions) => Promise<void>;
};

const AppDialogContext = createContext<AppDialogApi | null>(null);

export function AppDialogProvider({ children }: { children: ReactNode }) {
  const [dialog, setDialog] = useState<DialogRequest | null>(null);

  const close = useCallback((ok: boolean) => {
    setDialog((current) => {
      current?.resolve(ok);
      return null;
    });
  }, []);

  const api = useMemo<AppDialogApi>(
    () => ({
      confirm(message, options) {
        return new Promise<boolean>((resolve) => {
          setDialog({
            kind: "confirm",
            title: options?.title || "Please confirm",
            message,
            confirmLabel: options?.confirmLabel || "OK",
            cancelLabel: options?.cancelLabel || "Cancel",
            danger: options?.danger,
            resolve,
          });
        });
      },
      alert(message, options) {
        return new Promise<void>((resolve) => {
          setDialog({
            kind: "alert",
            title: options?.title || "Notice",
            message,
            confirmLabel: options?.confirmLabel || "OK",
            cancelLabel: "Cancel",
            resolve: () => resolve(),
          });
        });
      },
    }),
    [],
  );

  return (
    <AppDialogContext.Provider value={api}>
      {children}
      {dialog ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => close(false)}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="app-dialog-title"
            aria-describedby="app-dialog-message"
            className="w-full max-w-sm rounded-xl bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="app-dialog-title" className="font-display text-base font-bold tracking-tight text-wa-ink">
              {dialog.title}
            </h3>
            <p id="app-dialog-message" className="mt-2 whitespace-pre-line text-sm text-wa-muted">
              {dialog.message}
            </p>
            <div className={cn("mt-4 flex gap-2", dialog.kind === "confirm" ? "justify-end" : "justify-stretch")}>
              {dialog.kind === "confirm" ? (
                <button
                  type="button"
                  className="h-9 rounded-lg border border-wa-line px-3 text-sm font-medium hover:bg-wa-app"
                  onClick={() => close(false)}
                >
                  {dialog.cancelLabel}
                </button>
              ) : null}
              <button
                type="button"
                className={cn(
                  "h-9 rounded-lg px-3 text-sm font-medium text-white",
                  dialog.kind === "alert" ? "w-full" : "",
                  dialog.danger ? "bg-red-600 hover:bg-red-700" : "bg-wa-green hover:bg-wa-green-dark",
                )}
                onClick={() => close(true)}
              >
                {dialog.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </AppDialogContext.Provider>
  );
}

export function useAppDialog() {
  const value = useContext(AppDialogContext);
  if (!value) throw new Error("useAppDialog requires AppDialogProvider");
  return value;
}
