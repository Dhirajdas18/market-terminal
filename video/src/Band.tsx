import {interpolate, useCurrentFrame} from 'remotion';
import {C, easeOut, MONO, SANS, WIN} from './theme';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const ENTER = 12; // 400 ms
const EXIT = 7; // 233 ms: exits are shorter than entrances

// Opacity for an item shown from `from` to `to` (frames), fading in and out.
const fade = (frame: number, from: number, to: number, enter = ENTER) =>
  Math.min(
    interpolate(frame, [from, from + enter], [0, 1], {...clamp, easing: easeOut}),
    interpolate(frame, [to - EXIT, to], [1, 0], {...clamp, easing: easeOut}),
  );

type Line = {readonly text: string; readonly from: number; readonly to: number};

// One caption: the lead. Rises 14 px on the way in, lifts 8 px on the way out.
const CaptionLine = ({text, from, to}: Line) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        whiteSpace: 'nowrap',
        fontFamily: SANS,
        fontWeight: 650,
        fontSize: 54,
        letterSpacing: '-0.015em',
        color: C.text,
        opacity: fade(frame, from, to),
        translate: `0px ${
          interpolate(frame, [from, from + ENTER], [14, 0], {...clamp, easing: easeOut}) +
          interpolate(frame, [to - EXIT, to], [0, -8], {...clamp, easing: easeOut})
        }px`,
      }}
    >
      {text}
    </div>
  );
};

// The section label above the caption: decoration, so it only fades.
const Tag = ({text, from, to}: Line) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: WIN.left,
        top: 62,
        fontFamily: MONO,
        fontWeight: 500,
        fontSize: 24,
        letterSpacing: '0.08em',
        color: C.accent,
        opacity: fade(frame, from, to, 8),
      }}
    >
      {text}
    </div>
  );
};

type Key = {readonly keyName: string; readonly label: string; readonly from: number; readonly to: number};

// The key just pressed in the footage, shown as it happens.
const KeyChip = ({keyName, label, from, to}: Key) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        right: WIN.left,
        top: 50,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        opacity: fade(frame, from, to, 6),
      }}
    >
      <span
        style={{
          fontFamily: MONO,
          fontWeight: 500,
          fontSize: 30,
          color: C.text,
          background: C.raised,
          border: `2px solid ${C.accent}`,
          borderRadius: 10,
          padding: '4px 16px',
        }}
      >
        {keyName}
      </span>
      <span style={{fontFamily: SANS, fontWeight: 500, fontSize: 30, color: C.text2}}>{label}</span>
    </div>
  );
};

type Props = {
  readonly tag: string;
  readonly lines: readonly Line[];
  readonly keys?: readonly Key[];
};

// The caption band above the terminal window.
export const Band = ({tag, lines, keys = []}: Props) => (
  <>
    <Tag text={tag} from={lines[0].from - 2} to={lines[lines.length - 1].to} />
    <div style={{position: 'absolute', left: WIN.left, top: 100, height: 70}}>
      {lines.map((l) => (
        <CaptionLine key={l.text} text={l.text} from={l.from} to={l.to} />
      ))}
    </div>
    {keys.map((k) => (
      <KeyChip key={k.keyName} {...k} />
    ))}
    <div
      style={{
        position: 'absolute',
        right: WIN.left,
        top: WIN.top + WIN.height + 14,
        fontFamily: MONO,
        fontWeight: 500,
        fontSize: 20,
        color: C.text2,
        opacity: 0.7,
      }}
    >
      synthetic demo data
    </div>
  </>
);
