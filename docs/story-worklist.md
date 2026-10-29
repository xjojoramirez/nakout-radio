# Story worklist

Date: 2026-10-29

Status of the local track-story composition work.

## Completed

- 60 tracks composed across six batches, all reviewed and cleaned up.
- 115 tracks currently have `summary` and/or `story` locked in the local
  library: the 105 earlier locked tracks plus the 10 new ones.
- Every composed field has a source URL and a lock. Facts were corrected
  separately where the reviewer found provider/reissue dates, then locked and
  pushed with `scripts/push_facts.py`.
- Live carries the 115 pushed tracks' prose and the 105 reviewed fact fields
  (89 earlier plus 16 in this batch).
- The sixth batch also added 46 weekly chart rows for Jay-Z's Empire State Of
  Mind; those rows are locked locally and were pushed to live with a
  playlist-free chart-only payload. There is no dedicated chart push script
  yet.

## Remaining

- 320 tracks still have neither summary nor story.
- 564 tracks still have no story at all.

### Remaining by genre (no prose at all)

| Genre | Tracks |
|---|---|
| OPM Tunog Kalye | 170 |
| NU Metal | 49 |
| Pinoy Bato | 38 |
| Classic Love Songs | 34 |
| Emo Night | 23 |
| New Wave | 17 |
| Classic Rock | 7 |
| Traffic Jam | 4 |

## Next batch (10)

These are still empty and are the recommended next batch.

| Track | Genre | Album / year | Video ID | Note |
|---|---|---|---|---|
| Rivermaya — 214 | OPM Tunog Kalye | *Greatest Hits* / 2001 | `6yrmsZgW3RE` | compilation; check original album/date |
| Kitchie Nadal — Huwag Na Huwag Mong Sasabihin | OPM Tunog Kalye | *Kitchie Nadal* / 2004 | `fymhAXQ_aMI` | |
| Sugarfree — Hari Ng Sablay | OPM Tunog Kalye | *Dramachine* / 2004 | `rb3z8N5K1wQ` | |
| Up Dharma Down — Oo | OPM Tunog Kalye | *Fragmented* / 2006 | `cfWgS8a9UVs` | |
| Juan Dela Cruz Band — Himig Natin | Pinoy Bato | *SCE Himig Natin* / 2019 | `RU55BTejoZY` | reissue; check original album/date |
| Deftones — Knife Prty | NU Metal | *White Pony (20th Anniversary Deluxe Edition)* / 2020 | `tMqfNzaOf10` | reissue; original is 2000 |
| Slapshock — Wake Up | NU Metal | *Project 11-41* / 2014 | `07C4EOo-Byw` | |
| Céline Dion — I Love You | Classic Love Songs | *Falling into You* / 1996 | `rri790yZ84s` | |
| Saosin — Voices | Emo Night | *Saosin* / 2006 | `zgvKBDvLwC0` | |
| Jo Boxers — Just Got Lucky (Single Version) | New Wave | *Essential Boxerbeat* / 1996 | `z_tcVHyxJRA` | compilation; check original album/date |

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
6. If charts were added, push them with a playlist-free chart-only payload and
   keep `charts` locked locally. A reusable chart push script is still a
   follow-up.

## Notes

- `push_stories.py` carries only `summary`, `story` and `dj_note`.
  `push_facts.py` carries only fact fields that are locked locally, for the
  explicit video ids passed to it; it never pushes the whole library.
- Empty stories are intentionally left unlocked. The background Wikipedia
  pass can fill them; lock the empty `story` field in Studio if that decision
  must be permanent.
- A push always sends every locked story field, not just the latest batch.
- Charts are provider-derived and audited by the reviewer. Lock `charts` after
  a manual import so later enrichment does not replace the rows.
