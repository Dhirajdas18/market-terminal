import {Video} from '@remotion/media';
import type {CSSProperties, ReactNode} from 'react';
import {staticFile, useVideoConfig} from 'remotion';
import {CLIP} from './clips';
import {C, CLIP_H, CLIP_W, WIN, WIN_SCALE} from './theme';

type Props = {
  readonly start: number; // seconds into the session clip
  readonly style?: CSSProperties;
  readonly children?: ReactNode; // overlays, in clip pixels
};

// The terminal footage in a rounded window. Overlays are positioned in the clip's own pixels.
export const Window = ({start, style, children}: Props) => {
  const {fps} = useVideoConfig();
  return (
    <div
      style={{
        position: 'absolute',
        left: WIN.left,
        top: WIN.top,
        width: WIN.width,
        height: WIN.height,
        borderRadius: 14,
        overflow: 'hidden',
        background: C.surface,
        boxShadow: `0 0 0 1px ${C.grid}, 0 28px 80px rgba(0, 0, 0, 0.5)`,
        ...style,
      }}
    >
      <Video
        src={staticFile(CLIP)}
        trimBefore={Math.round(start * fps)}
        muted
        style={{width: WIN.width, height: WIN.height, display: 'block'}}
      />
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: CLIP_W,
          height: CLIP_H,
          scale: String(WIN_SCALE),
          transformOrigin: '0 0',
        }}
      >
        {children}
      </div>
    </div>
  );
};
