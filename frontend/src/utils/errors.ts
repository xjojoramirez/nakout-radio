import { ApiError } from "../api/client";

export function messageFor(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}
