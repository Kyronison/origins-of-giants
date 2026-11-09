import React from "react";
import { Composition } from "remotion";
import type { LabProps } from "./common";
import { Greyhound } from "./Greyhound";
import { PanAm } from "./PanAm";
import { Eastern } from "./Eastern";
import { InNOut } from "./InNOut";

/** Отдельная точка входа лаборатории шортсов: штатный src/index.ts её не импортирует, рендер конвейера не затронут. */
const FPS = 30;
const meta = ({ props }: { props: LabProps }) => ({ durationInFrames: Math.ceil((props.duration + 1.4) * FPS) });
const empty: LabProps = { words: [], duration: 10, voiceDur: 10, musicDur: 10 };

const comps: [string, React.FC<LabProps>][] = [["Greyhound", Greyhound], ["PanAm", PanAm], ["Eastern", Eastern], ["InNOut", InNOut]];

export const LabRoot: React.FC = () => (<>
  {comps.map(([id, C]) => <Composition key={id} id={id} component={C} width={1080} height={1920} fps={FPS} durationInFrames={300}
    defaultProps={empty} calculateMetadata={meta} />)}
</>);
