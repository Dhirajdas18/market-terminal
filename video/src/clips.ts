// Where each segment starts in video/public/clips/session.mp4, which `vhs docs/clips.tape` writes.
//
// Regenerating the demo (README's docs/img/demo.mp4 and demo.gif) needs Node, VHS, ttyd and ffmpeg;
// nothing in video/ runs in CI. From video/:
//      npm ci
//      npm run clips    # vhs docs/clips.tape: footage of every tab in video/public/clips/session.mp4
//      npm run render   # runs check-clip, then writes docs/img/demo.mp4, 1920 x 1080 at 30 fps
//      npm run gif      # docs/img/demo.gif, 1600 px wide at 12 fps
// check-clip stops the render if the clip's length differs from durationSeconds by more than 0.1 s,
// or if a segment start is not 0.05 to 0.25 s after a cut. The captions are in Demo.tsx; the numbers
// in its last scene are copied from the README's launch and exit table.
// Values are in seconds and live in clips.json, which scripts/check-clip.mjs also reads.
// The check runs before every `npm run render` and fails if the clip no longer matches.
//
// After re-recording the tape:
// 1. List the cuts (run from the repo root):
//      ffmpeg -i video/public/clips/session.mp4 -vf "select='gt(scene,0.01)',showinfo" -f null - 2>&1 | grep -o 'pts_time:[0-9.]*'
//    The tab switches are the cuts. Some cuts are not tab switches: y on the Chart segment, the Down and
//    Enter presses on the Watchlist segment, and q on the last segment. Name each cut by looking at frames
//    on either side of it, e.g.:
//      ffmpeg -ss <t> -i video/public/clips/session.mp4 -frames:v 1 /tmp/f.png
// 2. Set each segment's start to its tab-switch cut + 0.1 s, so no frame of the previous tab shows.
// 3. Set durationSeconds to the clip's length:
//      ffprobe -v error -show_entries format=duration -of csv=p=0 video/public/clips/session.mp4
// 4. If the y, Enter or q press moved, also move its caption and key-chip frames in Demo.tsx.
//    The presses are at about 9.28 s, 29.76 s and 34.36 s in the current clip.
import clips from './clips.json';

export const CLIP = clips.clip;
export const SEG = clips.starts;
