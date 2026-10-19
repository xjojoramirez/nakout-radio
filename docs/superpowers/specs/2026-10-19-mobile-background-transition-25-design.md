# Mobile background playback regression: transitions stalled by frozen timers (issue #25)

Date: 2026-10-19
Status: implemented on `fix/mobile-background-transition-25`
Device in the report: Android (Chrome)

## Problem

On a phone, audio played fine while the screen was on, but once the phone
went inactive or locked the next song never started until the listener
unlocked the phone. It could not be reproduced on desktop because a
desktop tab is never suspended the way a phone is when the screen locks.

## Root cause (regression analysis)

Timeline of the listener player:

| Date | Change | Transition mechanism |
| --- | --- | --- |
| 2026-10-12 | embeddable auto-retry | single iframe, event-driven (`ENDED` → reload) |
| 2026-10-13 | mobile resume fix (#4) | single iframe, events + 1 s reconcile tick |
| 2026-10-13 | song gap (#7) | single iframe + `setTimeout` gap start |
| 2026-10-14 | preload next song (#6) | **two iframes + `setTimeout`-driven swap** |

Before #7/#6, a track transition happened inside the *active* iframe with
`loadVideoById` on the `ENDED` event — no wall-clock timers were required,
so suspension of the page did not stall it.

After #7/#6, the transition depends on `setTimeout` firing at the song
boundary (`scheduleSwap` / `scheduleGapStart` in
`frontend/src/hooks/useYouTubePlayer.ts`). Mobile browsers freeze or
heavily throttle timers while the page is inactive (Android Chrome
intensively throttles background tabs; cross-origin iframe activity does
not reliably exempt the page). When the phone locks over a boundary:

1. the swap/gap timer never fires, so the preloaded track is never
   promoted;
2. the 1 s reconcile tick is frozen too, so nothing catches the miss;
3. on unlock, the player can sit on a stale/ended video while the
   broadcast has moved on.

## Fix design (all inside `useYouTubePlayer.ts`)

Make the pipeline self-heal after suspension, without removing the
pre-roll for the healthy foreground path:

1. **Shared promotion** — extract `performSwap` from `scheduleSwap` and
   let `startPreloaded` route through it when the pre-roll player already
   holds the next video while the active player is still on the previous
   one. The boundary timer and the recovery path now promote through the
   exact same sequence.
2. **Shared reconcile** — extract the effect body into `applyBroadcast`
   with a `forceLive` flag that skips the post-swap grace window, so the
   recovery path reconciles with the same rules as live frames.
3. **Visibility recovery** — on `visibilitychange` → visible:
   - clear stale swap/gap timers;
   - if a healthy pre-roll holds the next track and its boundary passed
     while the page was hidden (gap phase, or the live target runs past
     the current track's runtime), promote it at the live-calculated
     position;
   - otherwise reconcile the active player with the last frame and
     refresh the broadcast immediately instead of waiting for the
     (throttled) poll.
4. **Tick catch-up** — the 1 s tick reloads at the live position instead
   of seeking when the live target is at/past the track's runtime (a
   seek would land beyond the video or in a dead buffer), and advances
   an `ENDED` player when a frame already points at the next track.

## Tests (`useYouTubePlayer.dom.test.ts`)

Wall-clock time is driven with `vi.useFakeTimers()` + `vi.setSystemTime()`
where elapsed time matters.

- frozen swap timer: a fresh frame that still points at a track whose
  runtime has run out reloads at the live position instead of seeking;
- preload promotion when `visibilitychange` fires after the boundary
  passed while hidden;
- `visibilitychange` triggers an immediate broadcast refresh;
- the tick catches up past an ended track to the next one.

## Out of scope

Continuous audio *while the phone remains locked* is not achievable with
the YouTube iframe on iOS/Android; this fix guarantees a correct, fast
rejoin and keeps the pre-roll path available in the background on
Android, where Chrome may keep the tab running while audio plays. A
native audio pipeline (HTMLAudioElement + Media Session + self-hosted
stream) remains the only route to true lock-screen playback and is a
separate effort.
