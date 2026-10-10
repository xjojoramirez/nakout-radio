import { useEffect, useRef } from "react";

interface Props {
  message: string;
  onDone: () => void;
}

export function Toast({ message, onDone }: Props) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!message) return;
    timer.current = setTimeout(onDone, 2200);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onDone intentionally not a dep; restarting on a fresh callback would churn the timer at inline-arrow call sites
  }, [message]);

  if (!message) return null;
  return (
    <p className="toast" role="status">
      {message}
    </p>
  );
}
