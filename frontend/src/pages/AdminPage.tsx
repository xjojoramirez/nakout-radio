import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { NowPlayingPanel } from "../components/admin/NowPlayingPanel";
import { PlaylistsPanel } from "../components/admin/PlaylistsPanel";
import { SchedulePanel } from "../components/admin/SchedulePanel";
import { GenresPanel } from "../components/admin/GenresPanel";
import { Toast } from "../components/admin/Toast";
import { Tabs, type TabDef } from "../components/admin/Tabs";
import {
  PanelSkeleton,
  Skeleton,
  SkeletonForm,
} from "../components/admin/Skeleton";
import type { Genre } from "../types";
import { messageFor } from "../utils/errors";

type Phase = "checking" | "login" | "loading" | "ready";

export function AdminPage() {
  const [phase, setPhase] = useState<Phase>("checking");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<{ text: string; id: number } | null>(
    null,
  );
  const [genres, setGenres] = useState<Genre[]>([]);
  const [tab, setTab] = useState("now");
  const [playlistCount, setPlaylistCount] = useState<number | null>(null);
  const [slotCount, setSlotCount] = useState<number | null>(null);

  const loginEpoch = useRef(0);
  const noticeEpoch = useRef(0);

  const tabsDef: TabDef[] = [
    { id: "now", label: "Now Playing" },
    { id: "playlists", label: "Playlists", count: playlistCount },
    { id: "genres", label: "Genres", count: genres.length },
    { id: "schedule", label: "Schedule", count: slotCount },
  ];

  const refreshGenres = useCallback(async () => {
    try {
      setGenres(await api.listGenres());
    } catch {
      setGenres([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await api.session();
        if (!active) return;
        setPhase("loading");
        await refreshGenres();
        if (!active) return;
        setPhase("ready");
      } catch {
        // no valid session; show the login screen
        if (active) setPhase("login");
      }
    })();
    return () => {
      active = false;
    };
  }, [refreshGenres]);

  const login = async () => {
    const attempt = ++loginEpoch.current;
    try {
      await api.login(password);
      if (attempt !== loginEpoch.current) return;
      setPhase("loading");
      setError("");
      await refreshGenres();
      if (attempt !== loginEpoch.current) return;
      setPhase("ready");
    } catch (err) {
      if (attempt !== loginEpoch.current) return;
      setError(messageFor(err));
    }
  };

  const logout = async () => {
    loginEpoch.current += 1;
    try {
      await api.logout();
    } catch {
      // session may already be gone; ignore
    }
    setPhase("login");
    setGenres([]);
    setPassword("");
    setError("");
    setNotice(null);
    setPlaylistCount(null);
    setSlotCount(null);
  };

  const onNotice = (message: string) => {
    noticeEpoch.current += 1;
    setNotice({ text: message, id: noticeEpoch.current });
  };

  const onError = (message: string) => {
    setNotice(null);
    setError(message);
  };

  if (phase === "checking") {
    return (
      <div className="admin admin-page">
        <div className="admin-skeleton-card" aria-busy="true">
          <Skeleton variant="title" />
          <SkeletonForm count={1} />
        </div>
      </div>
    );
  }

  if (phase === "login") {
    return (
      <div className="admin admin-page">
        <form
          className="admin-login"
          onSubmit={(e) => {
            e.preventDefault();
            login();
          }}
        >
          <h1>Admin</h1>
          <p className="hint">Sign in to manage genres and playlists.</p>
          <label className="field">
            Password
            <input
              type="password"
              placeholder="Password"
              value={password}
              autoFocus
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary">
            Log in
          </button>
          {error && (
            <p className="error banner" role="alert">
              {error}
            </p>
          )}
          <a className="back-link" href="/">
            &larr; Back to radio
          </a>
        </form>
      </div>
    );
  }

  return (
    <div className="admin admin-page">
      <header className="admin-top">
        <div className="brand">
          Nakout<span>.</span>Radio <small>Admin</small>
        </div>
        <div className="top-r">
          <a className="back" href="/">
            &larr; Back to radio
          </a>
          <button type="button" className="btn btn-secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      <Toast
        key={notice?.id ?? 0}
        message={notice?.text ?? ""}
        onDone={() => setNotice(null)}
      />

      <Tabs tabs={tabsDef} active={tab} onChange={setTab} />

      <div
        id={`panel-${tab}`}
        className="admin-tabpanel"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        aria-busy={phase === "loading"}
      >
        {phase === "loading" ? (
          <PanelSkeleton tab={tab} />
        ) : (
          <>
            {tab === "now" && (
              <NowPlayingPanel
                genres={genres}
                onNotice={onNotice}
                onError={onError}
              />
            )}
            {tab === "playlists" && (
              <PlaylistsPanel
                genres={genres}
                onGenresChanged={refreshGenres}
                onNotice={onNotice}
                onError={onError}
                onCountChange={setPlaylistCount}
              />
            )}
            {tab === "genres" && (
              <GenresPanel
                genres={genres}
                onGenresChanged={refreshGenres}
                onNotice={onNotice}
                onError={onError}
              />
            )}
            {tab === "schedule" && (
              <SchedulePanel
                genres={genres}
                onNotice={onNotice}
                onError={onError}
                onCountChange={setSlotCount}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
