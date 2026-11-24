import type {ComponentProps, CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {Band} from './Band';
import {C, easeInOut, easeOut, MONO, SANS, WIN} from './theme';
import {Window} from './Window';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// Frames are 30 fps, counted from the start of each scene.

// ---------- Hook + Overview: one continuous shot ----------

const HOOK_EXIT = 78; // headline leaves, window settles into place
const SETTLE = 15; // 500 ms

const HookText = () => {
  const frame = useCurrentFrame();
  const exit = (f: number) => interpolate(f, [HOOK_EXIT, HOOK_EXIT + 7], [1, 0], {...clamp, easing: easeOut});
  const enter = (f: number, at: number, len: number) =>
    interpolate(f, [at, at + len], [0, 1], {...clamp, easing: easeOut});
  const rise = (f: number, at: number, len: number, px: number) =>
    interpolate(f, [at, at + len], [px, 0], {...clamp, easing: easeOut});
  return (
    <div style={{position: 'absolute', left: 120, top: 300, width: 1300}}>
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 750,
          fontSize: 100,
          lineHeight: 1.04,
          letterSpacing: '-0.03em',
          color: C.text,
          opacity: Math.min(enter(frame, 0, 9), exit(frame)),
          translate: `0px ${rise(frame, 0, 9, 20)}px`,
        }}
      >
        Your NSE day, reviewed
        <br />
        in one terminal.
      </div>
      <div
        style={{
          marginTop: 34,
          fontFamily: SANS,
          fontWeight: 500,
          fontSize: 40,
          color: C.text2,
          opacity: Math.min(enter(frame, 4, 12), exit(frame)),
          translate: `0px ${rise(frame, 4, 12, 12)}px`,
        }}
      >
        NIFTY 50 · breadth · sectors · who moved the index · risk
      </div>
      <div
        style={{
          display: 'inline-block',
          marginTop: 40,
          fontFamily: MONO,
          fontWeight: 500,
          fontSize: 32,
          color: C.text,
          background: C.raised,
          border: `2px solid ${C.accent}`,
          borderRadius: 12,
          padding: '8px 22px',
          opacity: Math.min(enter(frame, 8, 10), exit(frame)),
        }}
      >
        <span style={{color: C.accent}}>$</span> uv run mt
      </div>
    </div>
  );
};

const HookScrim = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        background:
          'linear-gradient(90deg, rgba(17,17,16,0.95) 0%, rgba(17,17,16,0.86) 48%, rgba(17,17,16,0.3) 100%)',
        opacity: interpolate(frame, [HOOK_EXIT, HOOK_EXIT + SETTLE], [1, 0], {...clamp, easing: easeOut}),
      }}
    />
  );
};

// The NIFTY 50 tile, in clip pixels.
const TileRing = ({from, to}: {readonly from: number; readonly to: number}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: 18,
        top: 129,
        width: 566,
        height: 154,
        borderRadius: 10,
        boxShadow: `0 0 0 3px ${C.accent}, 0 0 28px rgba(57, 135, 229, 0.35)`,
        opacity: Math.min(
          interpolate(frame, [from, from + 10], [0, 1], {...clamp, easing: easeOut}),
          interpolate(frame, [to - 7, to], [1, 0], {...clamp, easing: easeOut}),
        ),
      }}
    />
  );
};

const OverviewWindow = ({start}: {readonly start: number}) => {
  const frame = useCurrentFrame();
  const centreShift = 540 - (WIN.top + WIN.height / 2);
  return (
    <Window
      start={start}
      style={{
        scale: String(
          interpolate(frame, [HOOK_EXIT + 2, HOOK_EXIT + 2 + SETTLE], [1.2, 1], {...clamp, easing: easeInOut}),
        ),
        translate: `0px ${interpolate(frame, [HOOK_EXIT + 2, HOOK_EXIT + 2 + SETTLE], [centreShift, 0], {
          ...clamp,
          easing: easeInOut,
        })}px`,
      }}
    >
      <TileRing from={108} to={196} />
    </Window>
  );
};

export const HookOverview = ({start}: {readonly start: number}) => (
  <AbsoluteFill style={{background: C.canvas}}>
    <OverviewWindow start={start} />
    <HookScrim />
    <HookText />
    <Band
      tag="01 · OVERVIEW"
      lines={[{text: 'Six markets: day, week, YTD and the 52-week range', from: 94, to: 196}]}
    />
  </AbsoluteFill>
);

// ---------- A tab: footage plus captions ----------

type TabProps = {readonly start: number} & ComponentProps<typeof Band>;

export const Tab = ({start, ...band}: TabProps) => (
  <AbsoluteFill style={{background: C.canvas}}>
    <Window start={start} />
    <Band {...band} />
  </AbsoluteFill>
);

// ---------- Trust beat: the README's measured numbers ----------

type Stat = {readonly value: string; readonly label: string; readonly from: number; readonly to: number};

const StatChip = ({value, label, from, to}: Stat) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        width: 500,
        padding: '26px 28px',
        background: C.raised,
        border: `1px solid ${C.grid}`,
        borderRadius: 16,
        boxShadow: '0 18px 50px rgba(0, 0, 0, 0.5)',
        opacity: Math.min(
          interpolate(frame, [from, from + 12], [0, 1], {...clamp, easing: easeOut}),
          interpolate(frame, [to - 7, to], [1, 0], {...clamp, easing: easeOut}),
        ),
        translate: `0px ${interpolate(frame, [from, from + 12], [16, 0], {...clamp, easing: easeOut})}px`,
      }}
    >
      <div style={{fontFamily: MONO, fontWeight: 500, fontSize: 64, color: C.text}}>{value}</div>
      <div style={{marginTop: 8, fontFamily: SANS, fontWeight: 500, fontSize: 28, color: C.text2, whiteSpace: 'nowrap'}}>{label}</div>
    </div>
  );
};

const TrustScrim = ({to}: {readonly to: number}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: WIN.left,
        top: WIN.top,
        width: WIN.width,
        height: WIN.height,
        borderRadius: 14,
        background: 'rgba(17, 17, 16, 0.55)',
        opacity: Math.min(
          interpolate(frame, [4, 16], [0, 1], {...clamp, easing: easeOut}),
          interpolate(frame, [to - 7, to], [1, 0], {...clamp, easing: easeOut}),
        ),
      }}
    />
  );
};

const Footnote = ({from, to}: {readonly from: number; readonly to: number}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: 812,
        textAlign: 'center',
        fontFamily: SANS,
        fontWeight: 500,
        fontSize: 26,
        color: C.text2,
        opacity: Math.min(
          interpolate(frame, [from, from + 10], [0, 1], {...clamp, easing: easeOut}),
          interpolate(frame, [to - 7, to], [1, 0], {...clamp, easing: easeOut}),
        ),
      }}
    >
      Measured on an Apple Silicon Mac with the cache in place (README, Running it)
    </div>
  );
};

export const Trust = ({start}: {readonly start: number}) => (
  <AbsoluteFill style={{background: C.canvas}}>
    <Window start={start} />
    <TrustScrim to={99} />
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: 540,
        display: 'flex',
        justifyContent: 'center',
        gap: 30,
      }}
    >
      <StatChip value="0.58 s" label="start to first screen" from={8} to={99} />
      <StatChip value="0.0%" label="CPU while idle" from={14} to={99} />
      <StatChip value="0.32 s" label="q to exit, nothing left running" from={30} to={99} />
    </div>
    <Footnote from={8} to={99} />
    <Band
      tag="07 · FOOTPRINT"
      lines={[{text: "It runs only while it's open", from: 6, to: 99}]}
      keys={[{keyName: 'q', label: 'quit', from: 30, to: 99}]}
    />
  </AbsoluteFill>
);

// ---------- Outro ----------

const OutroLine = ({at, rise, children, style}: {readonly at: number; readonly rise: number; readonly children: ReactNode; readonly style: CSSProperties}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        ...style,
        opacity: interpolate(frame, [at, at + 12], [0, 1], {...clamp, easing: easeOut}),
        translate: `0px ${interpolate(frame, [at, at + 12], [rise, 0], {...clamp, easing: easeOut})}px`,
      }}
    >
      {children}
    </div>
  );
};

export const Outro = () => (
  <AbsoluteFill
    style={{background: C.canvas, alignItems: 'center', justifyContent: 'center', flexDirection: 'column'}}
  >
    <OutroLine
      at={4}
      rise={18}
      style={{fontFamily: SANS, fontWeight: 750, fontSize: 112, letterSpacing: '-0.03em', color: C.text}}
    >
      market-terminal
    </OutroLine>
    <OutroLine at={9} rise={10} style={{marginTop: 26, fontFamily: MONO, fontWeight: 500, fontSize: 38, color: C.text2}}>
      github.com/Dhirajdas18/market-terminal
    </OutroLine>
    <OutroLine
      at={13}
      rise={0}
      style={{
        marginTop: 48,
        fontFamily: MONO,
        fontWeight: 500,
        fontSize: 36,
        color: C.text,
        background: C.raised,
        border: `2px solid ${C.accent}`,
        borderRadius: 12,
        padding: '10px 26px',
      }}
    >
      <span style={{color: C.accent}}>$</span> uv run mt
    </OutroLine>
  </AbsoluteFill>
);
