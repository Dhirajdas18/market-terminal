// Where each segment starts in video/public/clips/session.mp4 (written by `vhs docs/clips.tape`),
// in seconds. Found with ffmpeg scene detection on the cuts; each start is 0.1 s after its cut so
// no frame of the previous tab shows. Re-check these after re-recording the tape.
export const CLIP = 'clips/session.mp4';

export const SEG = {
  overview: 0,
  chart: 7.42, // y pressed at 9.28
  movers: 12.82,
  breadth: 17.22,
  sectors: 21.62,
  watchlist: 26.98, // Enter on HDFCBANK at 29.76
  quit: 33.3, // q pressed at 34.36; the recording ends at 37.08
};
