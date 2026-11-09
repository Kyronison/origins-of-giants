import React from "react";
import { Composition, Still } from "remotion";
import { S, SpaceSpec } from "./theme";
import { SpaceFilm, SpaceSheet } from "./Film";
import { SpaceAvatar, SpaceBanner, BrandSpec } from "./Brand";

const demo: SpaceSpec = { duration: 6, voice: null, shots: [
  { id: "d1", type: "compare", start: 0, end: 6, tag: "established", kicker: "demo", data: { from: 0, bodies: [
    { name: "Earth", r: 0.009158, color: "#4f8fd6", kind: "planet", callout: true }, { name: "Jupiter", r: 0.1005, color: "#d9a066", kind: "planet", callout: true },
    { name: "The Sun", r: 1, color: "#ffd34d", label: "109 Earths wide" }] } }] };

export const SpaceRoot = () => (
  <>
    <Composition id="Space" component={SpaceFilm} fps={S.fps} width={S.W} height={S.H} defaultProps={{ spec: demo }}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.ceil(props.spec.duration * S.fps) })} />
    <Composition id="SpaceSheet" component={SpaceSheet} fps={S.fps} width={S.W} height={S.H} defaultProps={{ spec: demo }}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.max(1, props.spec.shots.length) })} />
    <Still id="SpaceAvatar" component={SpaceAvatar} width={800} height={800} defaultProps={{ spec: { name: "Absurd Scale", mark: "A" } as BrandSpec }} />
    <Still id="SpaceBanner" component={SpaceBanner} width={2560} height={1440} defaultProps={{ spec: { name: "Absurd Scale", mark: "A", tagline: "The universe, measured honestly" } as BrandSpec }} />
  </>
);
