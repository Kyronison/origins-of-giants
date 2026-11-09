import { AbsoluteFill, Audio, Easing, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { D, Tag } from "./dossier";
import type { HookSpec, HookShot } from "./ShortHook";

/** Calm, native dossier Shorts. Diagrams are editorial illustrations, never evidence photos. */
export type StoryPanel = {
  start: number; end: number; layout: "photo" | "ownership" | "radius" | "flow";
  kicker: string; headline: string; footnote: string; image?: string; src?: string;
  metric?: { value: string; label: string; source: string; at?: number };
  nodes?: string[]; activeAt?: number[];
};
const ease = (frame: number, start = 0, length = 24) => interpolate(frame, [start, start + length], [0, 1], {
  extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic),
});
const Factory = () => <g fill="none" stroke="currentColor" strokeWidth={5} strokeLinejoin="round">
  <path d="M-62 48V-20L-20-44V-20L22-44V48Z M-48-27V-72H-27V-41 M-48 12H-30M-9 12H9" />
  <path d="M22 48H62V-22H22M38 10H48M38 30H48" />
</g>;
const Store = () => <g fill="none" stroke="currentColor" strokeWidth={5} strokeLinejoin="round">
  <path d="M-58-6L-44-42H44L58-6Z M-50-6V48H50V-6 M-17 48V12H17V48" />
  <path d="M-58-6Q-44 15-29-6Q-14 15 0-6Q14 15 29-6Q44 15 58-6 M-38-42L-29-6M0-42V-6M38-42L29-6" />
</g>;
const Truck = () => <g fill={D.dark} stroke="currentColor" strokeWidth={5} strokeLinejoin="round">
  <path d="M-48-23H12V20H-48Z M12-9H34L49 6V20H12" /><circle cx={-28} cy={23} r={10} /><circle cx={31} cy={23} r={10} />
</g>;
const Ownership = ({ frame, labels }: { frame: number; labels: string[] }) => {
  const draw = ease(frame, 12, 60);
  return <svg width={844} height={620} viewBox="0 0 844 620" style={{ color: D.cream }}>
    <rect x={222} y={70} width={400} height={128} rx={4} fill={D.cream} />
    <text x={422} y={148} textAnchor="middle" fill={D.brown} fontFamily={D.serif} fontSize={42}>{labels[0] ?? "Family"}</text>
    <path d="M422 198V330M212 330H632M212 330V405M422 330V405M632 330V405" stroke={D.muted} strokeWidth={4} fill="none"
      strokeDasharray={1050} strokeDashoffset={1050 * (1 - draw)} />
    {[212,422,632].map((x,k) => <g key={k} transform={`translate(${x} 463)`} opacity={ease(frame, 55 + k*12, 22)}><Store /></g>)}
    <text x={422} y={595} textAnchor="middle" fill={D.muted} fontFamily={D.mono} fontSize={28}>{labels[1] ?? "Company-owned restaurants"}</text>
  </svg>;
};
const Radius = ({ frame, panel }: { frame: number; panel: StoryPanel }) => {
  const ring= ease(frame, 32, 65); const route=ease(frame, 115, 55);
  // A diagram of the stated policy, not a geographic map or an exact route calculation.
  const tx=422+route*214, ty=408-route*150;
  return <svg width={844} height={650} viewBox="0 0 844 780" style={{ color: D.cream }}>
    {[90,190,290].map(r => <circle key={r} cx={422} cy={408} r={r} stroke={D.rule} fill="none" strokeWidth={2} />)}
    <circle cx={422} cy={408} r={290} stroke={D.cream} fill="none" strokeWidth={4} strokeDasharray={1823} strokeDashoffset={1823*(1-ring)} transform="rotate(-90 422 408)" />
    <g transform="translate(422 408)"><Factory /></g>
    <text x={422} y={520} textAnchor="middle" fill={D.muted} fontSize={27} fontFamily={D.mono}>Distribution center</text>
    {[[642,238],[228,239],[216,588]].map(([x,y],k) => <g key={k} transform={`translate(${x} ${y}) scale(.63)`} opacity={ease(frame, 92+k*14, 24)}><Store /></g>)}
    <path d="M450 382L624 255" stroke={D.muted} strokeWidth={3} fill="none" strokeDasharray="7 9" opacity={ease(frame,100)} />
    <g transform={`translate(${tx} ${ty}) scale(.48)`} opacity={ease(frame,115)}><Truck /></g>
    <g opacity={ease(frame,195,22)}><path d="M156 716L197 757M197 716L156 757" stroke={D.ox} strokeWidth={6}/>
      <text x={229} y={750} fill={D.cream} fontSize={29} fontFamily={D.mono}>{panel.nodes?.[0] ?? "No frozen ingredients"}</text></g>
  </svg>;
};
const Flow = ({frame, panel}: {frame: number; panel: StoryPanel}) => {
  const labels=panel.nodes??[];
  return <svg width={844} height={690} viewBox="0 0 844 690">
    {labels.map((label,k)=> <g key={k} opacity={ease(frame,(panel.activeAt?.[k]??k*1.7)*30)}>
      {k>0&&<path d={`M422 ${k*200-54}V${k*200-6}`} fill="none" stroke={D.muted} strokeWidth={4}/>}
      <rect x={100} y={20+k*200} width={644} height={125} fill={D.cream} rx={4}/>
      <text x={422} y={100+k*200} textAnchor="middle" fill={D.brown} fontFamily={D.serif} fontSize={Math.min(38,590/Math.max(label.length*.56,1))}>{label}</text>
    </g>)}
  </svg>;
};
const Panel = ({panel}: {panel:StoryPanel}) => {
  const frame=useCurrentFrame();const {fps}=useVideoConfig();const fade=ease(frame,0,18);
  const textFade=1-ease(frame,Math.round((panel.end-panel.start)*fps)-9,9);
  const metric=panel.metric; const metricFade=ease(frame,(metric?.at??0)*fps);
  return <AbsoluteFill style={{opacity:fade,background:D.dark,backgroundImage:"radial-gradient(ellipse at 25% 25%,#34261c 0%,transparent 65%)"}}>
    <div style={{position:"absolute",left:72,right:164,top:259,fontFamily:D.mono,fontSize:26,color:D.muted,letterSpacing:2,opacity:textFade}}>{panel.kicker.toUpperCase()}</div>
    <div style={{position:"absolute",left:72,right:164,top:315,fontFamily:D.serif,fontWeight:700,fontSize:64,lineHeight:1.12,color:D.cream,opacity:textFade}}>{panel.headline}</div>
    <div style={{position:"absolute",left:72,top:495,width:844}}>
      {panel.layout==="photo"&&(panel.image||panel.src)&&<div style={{padding:12,background:D.photo,transform:`translateY(${8*(1-fade)}px) rotate(-.5deg)`}}>
        {panel.src?<OffthreadVideo muted src={staticFile(panel.src)} style={{display:"block",width:820,height:460,objectFit:"cover"}}/>:
        <Img src={staticFile(panel.image!)} style={{display:"block",width:820,height:460,objectFit:"cover",transform:`scale(${1+Math.min(frame/(fps*10),1)*.025})`}} />}
      </div>}
      {panel.layout==="ownership"&&<Ownership frame={frame} labels={panel.nodes??[]} />}
      {panel.layout==="radius"&&<Radius frame={frame} panel={panel} />}
      {panel.layout==="flow"&&<Flow frame={frame} panel={panel} />}
    </div>
    {metric&&<div style={{position:"absolute",left:72,right:164,top:panel.layout==="radius"?1160:1040,opacity:metricFade*textFade,transform:`translateY(${12*(1-metricFade)}px)`}}>
      <span style={{fontFamily:D.serif,fontSize:panel.layout==="radius"?68:116,fontWeight:700,color:D.cream}}>{metric.value}</span>
      <div style={{fontFamily:D.mono,fontSize:30,lineHeight:1.3,color:D.muted,marginTop:8}}>{metric.label}</div>
      <div style={{fontFamily:D.mono,fontSize:22,color:D.muted,marginTop:17}}>{metric.source}</div>
    </div>}
    <div style={{position:"absolute",left:72,right:164,top:1390,fontFamily:D.mono,fontSize:22,lineHeight:1.4,color:D.muted,opacity:textFade}}>{panel.footnote}</div>
  </AbsoluteFill>;
};
const CalmPhoto = ({shot, length}: {shot:HookShot;length:number}) => {
  const f=useCurrentFrame();const fade=ease(f,0,18);
  const style={width:"100%",height:"100%",objectFit:"cover" as const,objectPosition:`${(shot.focus_xy?.[0]??.5)*100}% ${(shot.focus_xy?.[1]??.5)*100}%`};
  return <AbsoluteFill style={{opacity:fade,padding:"330px 164px 900px 72px"}}>
    <div style={{height:"100%",border:`12px solid ${D.photo}`,overflow:"hidden",transform:`scale(${1+.035*f/Math.max(length,1)})`}}>
      {shot.src?<OffthreadVideo src={staticFile(shot.src)} muted style={style}/>:shot.image?<Img src={staticFile(shot.image)} style={style}/>:null}
    </div>
    <div style={{position:"absolute",left:72,right:164,top:1040,color:D.muted,fontFamily:D.mono,fontSize:22}}>{shot.year?`${shot.year} · `:""}{shot.credit}</div>
  </AbsoluteFill>;
};
export const ShortStory:React.FC<{spec:HookSpec}> = ({spec}) => {
  const f=useCurrentFrame();const {fps}=useVideoConfig();const t=f/fps;const total=Math.ceil(spec.duration*fps);
  const cap=spec.captions.find(c=>t>=c.start&&t<c.end);
  return <AbsoluteFill style={{background:D.dark,color:D.cream,
    backgroundImage:"radial-gradient(ellipse at 25% 25%,#34261c 0%,transparent 65%),repeating-linear-gradient(0deg,transparent 0,transparent 79px,rgba(168,151,127,.035) 80px)"}}>
    <Audio src={staticFile(spec.voice)}/>
    {spec.music&&<Audio src={staticFile(spec.music.src)} startFrom={Math.round((spec.music.offset??0)*fps)} volume={fr=>(spec.music?.volume??.04)*interpolate(fr,[0,30,total-60,total],[0,1,1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}/>}
    <div style={{position:"absolute",top:170,left:72}}><Tag style={{padding:"12px 18px",boxShadow:"none"}}><span style={{fontFamily:D.mono,fontSize:25,letterSpacing:2}}>{spec.channel.toUpperCase()}</span></Tag></div>
    {spec.story_panels?.length?spec.story_panels.map((panel,k)=><Sequence key={k} from={Math.round(panel.start*fps)} durationInFrames={Math.ceil((panel.end-panel.start)*fps)+18}><Panel panel={panel}/></Sequence>):
      spec.shots.map((shot,k)=><Sequence key={k} from={Math.round(shot.start*fps)} durationInFrames={Math.max(1,Math.round((shot.end-shot.start)*fps))}><CalmPhoto shot={shot} length={(shot.end-shot.start)*fps}/></Sequence>)}
    {!spec.story_panels?.length&&cap&&t<spec.end.start&&<div style={{position:"absolute",left:72,right:164,top:1160,fontFamily:D.serif,fontSize:60,lineHeight:1.25}}>{cap.words.map(w=>w.w).join(" ")}</div>}
    {t>=spec.end.start&&<AbsoluteFill style={{background:D.dark,opacity:ease(f-spec.end.start*fps),padding:"380px 164px 0 72px"}}>
      {spec.end.thumb&&<Img src={staticFile(spec.end.thumb)} style={{width:844,border:`10px solid ${D.photo}`}}/>}
      <div style={{marginTop:65,fontFamily:D.serif,fontSize:67,lineHeight:1.18}}>{spec.end.line1}</div>
      <div style={{marginTop:30,fontFamily:D.mono,fontSize:31,color:D.muted,lineHeight:1.3}}>{spec.end.line2}</div>
    </AbsoluteFill>}
  </AbsoluteFill>;
};
