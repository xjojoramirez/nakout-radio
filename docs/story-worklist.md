# Story worklist

Date: 2026-10-28

Status of the local track-story composition work.

## Completed

- 50 tracks composed across five batches, all reviewed and cleaned up.
- 105 tracks currently have `summary` and/or `story` locked in the local
  library: the 55 earlier locked tracks plus the 50 new ones.
- Every composed field has a source URL and a lock. Facts were corrected
  separately where the reviewer found provider/reissue dates, then locked and
  pushed with `scripts/push_facts.py`.
- Live carries the 105 pushed tracks' prose and the 89 reviewed fact fields.

## Remaining

- 330 tracks still have neither summary nor story.
- 569 tracks still have no story at all.

### Remaining by genre (no prose at all)

| Genre | Tracks |
|---|---|
| OPM Tunog Kalye | 175 |
| NU Metal | 50 |
| Pinoy Bato | 39 |
| Classic Love Songs | 35 |
| Emo Night | 24 |
| New Wave | 18 |
| Classic Rock | 7 |
| Traffic Jam | 5 |

## Next batch (10)

These are still empty and are the recommended next batch.

| Track | Genre | Album / year | Video ID | Note |
|---|---|---|---|---|
| After Image — Mangarap Ka | OPM Tunog Kalye | *Greatest Hits* / 1996 | `__NRDwlfetI` | compilation; check original album/date |
| Gloc-9 — Hari Ng Tondo | OPM Tunog Kalye | *MKNM* / 2017 | `PLvbweV2RG0` | |
| Cueshé — Pangako | OPM Tunog Kalye | *Life* / 2010 | `jc14fnl6u5g` | |
| Brownman Revival — Yakap Sa Dilim | OPM Tunog Kalye | *Ayos Din* / 2007 | `i9qUgUBzU8Q` | |
| Deftones — Bloody Cape | NU Metal | *Deftones* / 2003 | `5UCHWwSN3Fw` | |
| Siakol — Bakit Ba? | Pinoy Bato | *Tayo Na Sa Paraiso* / 2005 | `bEWeMAsIFYA` | |
| Chicosci — A Promise | Emo Night | *Chicosci* / 2023 | `rTPkp7dzKAM` | 2023 streaming edition; original is 2006 |
| Fra Lippo Lippi — Every Time I See You | New Wave | *Songs* / 2016 | `atqNGhihhbY` | compilation; check original album/date |
| Calloway — You Are My Everything | Classic Love Songs | *All The Way* / 2026 | `8HrJHAnclhk` | reissue-looking year; verify |
| Jay-Z — Empire State Of Mind | Traffic Jam | *The Blueprint 3* / 2009 | `_ydMlTassYc` | |

## Resume workflow

1. Pull live into local if the live library changed:
   `python scripts/pull_library.py --from https://nakout.com --to http://127.0.0.1:8011 ...`
2. Compose the batch with the `track-info-composer` agent, one track at a time.
3. Audit with the `track-details-reviewer` agent, one reviewer per five tracks.
4. Clean up fact/edition findings locally, update `sources`, and lock the
   corrected fact fields.
5. Dry-run and apply the facts for the reviewed ids:
   `python scripts/push_facts.py --ids-file <ids> --dry-run`, then without
   `--dry-run`. Then push prose with `scripts/push_stories.py`, dry-run first.
   Live import must be enabled only for the pushes, then disabled again.

## Notes

- `push_stories.py` carries only `summary`, `story` and `dj_note`.
  `push_facts.py` carries only fact fields that are locked locally, for the
  explicit video ids passed to it; it never pushes the whole library.
- Empty stories are intentionally left unlocked. The background Wikipedia
  pass can fill them; lock the empty `story` field in Studio if that decision
  must be permanent.
- A push always sends every locked story field, not just the latest batch.
