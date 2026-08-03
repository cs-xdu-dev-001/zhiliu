import { useEffect, useRef } from "react";

const focusableSelector = [
  "button:not(:disabled)",
  "a[href]",
  "input:not(:disabled)",
  "select:not(:disabled)",
  "textarea:not(:disabled)",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function useModalDialog<T extends HTMLElement>(open: boolean, onClose: () => void, locked = false) {
  const dialogRef = useRef<T>(null);
  const closeRef = useRef(onClose);
  const lockedRef = useRef(locked);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const wasOpenRef = useRef(false);
  closeRef.current = onClose;
  lockedRef.current = locked;

  function rememberTrigger(trigger?: HTMLElement) {
    if (trigger) previousFocusRef.current = trigger;
    else if (document.activeElement instanceof HTMLElement) previousFocusRef.current = document.activeElement;
  }

  useEffect(() => {
    if (!open && wasOpenRef.current && previousFocusRef.current?.isConnected) previousFocusRef.current.focus();
    wasOpenRef.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (!previousFocusRef.current && document.activeElement instanceof HTMLElement) previousFocusRef.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => {
      const preferred = dialogRef.current?.querySelector<HTMLElement>("[autofocus]");
      const first = dialogRef.current?.querySelector<HTMLElement>(focusableSelector);
      (preferred ?? first)?.focus();
    });

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (!lockedRef.current) closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? []);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return { dialogRef, rememberTrigger };
}
