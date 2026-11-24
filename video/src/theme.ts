import {loadFont} from '@remotion/fonts';
import {Easing} from 'remotion';
import interLatin from '@fontsource-variable/inter/files/inter-latin-wght-normal.woff2';
import interLatinExt from '@fontsource-variable/inter/files/inter-latin-ext-wght-normal.woff2';
import monoLatin from '@fontsource/jetbrains-mono/files/jetbrains-mono-latin-500-normal.woff2';

// The app's colour tokens (src/mt/app.tcss, src/mt/widgets.py), plus one darker canvas so the
// terminal window reads as a window.
export const C = {
  canvas: '#111110',
  surface: '#1a1a19',
  raised: '#242422',
  grid: '#2e2d2b',
  text: '#f0efec',
  text2: '#c3c2b7',
  accent: '#3987e5',
  up: '#199e70',
  down: '#e66767',
  warn: '#c98500',
};

export const SANS = 'Inter';
export const MONO = 'JetBrains Mono';

// Strong ease-out for entrances and exits, strong ease-in-out for on-screen moves.
export const easeOut = Easing.bezier(0.23, 1, 0.32, 1);
export const easeInOut = Easing.bezier(0.77, 0, 0.175, 1);

// Fonts come from node_modules (bundled), so rendering needs no network.
Promise.all([
  loadFont({family: SANS, url: interLatin, weight: '100 900'}),
  loadFont({
    family: SANS,
    url: interLatinExt,
    weight: '100 900',
    unicodeRange: 'U+0100-02BA, U+20A0-20AB, U+20AD-20C0, U+2113',
  }),
  loadFont({family: MONO, url: monoLatin, weight: '500'}),
]);

// The window the footage sits in: the 1760 x 880 VHS clip shown at 90%.
export const CLIP_W = 1760;
export const CLIP_H = 880;
export const WIN_SCALE = 0.9;
export const WIN = {
  left: (1920 - CLIP_W * WIN_SCALE) / 2,
  top: 228,
  width: CLIP_W * WIN_SCALE,
  height: CLIP_H * WIN_SCALE,
};
