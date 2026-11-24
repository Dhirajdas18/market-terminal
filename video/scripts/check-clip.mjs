// Fails the render when video/public/clips/session.mp4 no longer matches src/clips.json:
// its length differs by more than 0.1 s, or a segment start is not just after a cut.
// To fix it, follow the procedure at the top of src/clips.ts.
import {execFileSync, spawnSync} from 'node:child_process';
import {existsSync, readFileSync} from 'node:fs';

const here = new URL('..', import.meta.url).pathname;
const cfg = JSON.parse(readFileSync(`${here}src/clips.json`, 'utf8'));
const clip = `${here}public/${cfg.clip}`;
const fail = (msg) => {
  console.error(`check-clip: ${msg}\nFollow the procedure at the top of video/src/clips.ts.`);
  process.exit(1);
};

if (!existsSync(clip)) fail(`${clip} is missing; run \`npm run clips\` first.`);

const duration = Number(
  execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', clip], {
    encoding: 'utf8',
  }),
);
if (Math.abs(duration - cfg.durationSeconds) > 0.1) {
  fail(`the clip is ${duration.toFixed(2)} s, clips.json expects ${cfg.durationSeconds} s.`);
}

// Same detection as in the procedure: every visual cut, with its time.
const log = spawnSync(
  'ffmpeg',
  ['-hide_banner', '-i', clip, '-vf', "select='gt(scene,0.01)',showinfo", '-f', 'null', '-'],
  {encoding: 'utf8'},
).stderr;
const cuts = [...String(log).matchAll(/pts_time:([0-9.]+)/g)].map((m) => Number(m[1]));
for (const [name, start] of Object.entries(cfg.starts)) {
  if (start === 0) continue;
  const ok = cuts.some((c) => c <= start - 0.05 && c > start - 0.25);
  if (!ok) fail(`no cut between 0.05 s and 0.25 s before the ${name} start (${start} s); cuts: ${cuts.join(', ')}.`);
}
console.log(`check-clip: ok (${duration.toFixed(2)} s, ${Object.keys(cfg.starts).length} segments)`);
