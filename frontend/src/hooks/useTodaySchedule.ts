import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ScheduleToday } from "../types";

export const REFRESH_MS = 5 * 60 * 1000;

export function useTodaySchedule(): { today: ScheduleToday | null } {
  const [today, setToday] = useState<ScheduleToday | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .scheduleToday()
        .then((data) => {
          if (!cancelled) setToday(data);
        })
        .catch(() => {
          // keep the last known schedule; the next tick retries
        });
    };
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { today };
}
