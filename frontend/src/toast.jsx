import { useEffect, useState } from "react";
import { CheckCircleIcon, XIcon } from "./components/icons";

// Tiny event-based toast store (no provider plumbing needed).
let listeners = [];

export function notify(message, type = "success") {
  listeners.forEach((fn) => fn(message, type));
}

function useToasts() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const add = (message, type) => {
      const id = `${Date.now()}-${Math.random()}`;
      setToasts((list) => [...list, { id, message, type }]);
      setTimeout(() => {
        setToasts((list) => list.filter((t) => t.id !== id));
      }, 3400);
    };
    listeners.push(add);
    return () => {
      listeners = listeners.filter((fn) => fn !== add);
    };
  }, []);

  return toasts;
}

export function ToastContainer() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;
  return (
    <div className="toast-container" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.type === "error" ? (
            <XIcon className="text-sm shrink-0" />
          ) : (
            <CheckCircleIcon className="text-sm shrink-0" />
          )}
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}