import React from "react";
import { Composition, registerRoot } from "remotion";
import type { MotionProps } from "./common";
import { Blocks } from "./Blocks";
import { Globe } from "./Globe";
import { Versus } from "./Versus";

/** Точка входа моушен-шортсов: рендерит orchestrator/stages/motion_shorts.py. Штатный src/index.ts её не импортирует. */
const FPS = 30;
const meta = ({ props }: { props: MotionProps }) => ({ durationInFrames: Math.ceil((props.duration + 1.4) * FPS) });
const empty: MotionProps = { words: [], duration: 10, voiceDur: 10, musicDur: 10, music: false, title: "", data: {} };
const comps: [string, React.FC<MotionProps<any>>][] = [["Blocks", Blocks], ["Globe", Globe], ["Versus", Versus]];

const Root: React.FC = () => React.createElement(React.Fragment, null,
  ...comps.map(([id, C]) => React.createElement(Composition as any, { key: id, id, component: C, width: 1080, height: 1920, fps: FPS, durationInFrames: 300, defaultProps: empty, calculateMetadata: meta })));

registerRoot(Root);
