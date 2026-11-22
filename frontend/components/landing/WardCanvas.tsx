"use client";

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { Bed, type BedStatus } from "./scene/Bed";
import { Skeleton } from "./scene/Skeleton";
import { AlertRing, QrCard, WallCamera } from "./scene/Props";
import { C, ramp } from "./scene/palette";

// The bed the story follows, and where the patient lands beside it.
const FOCUS_X = -1.6;
const BEDS_X = [-4.8, -1.6, 1.6, 4.8];

// Camera keyframes per chapter: hero, admit, watch, alert, overview.
const KEYS: { pos: [number, number, number]; look: [number, number, number] }[] = [
  { pos: [15.5, 14, 18.5], look: [-0.9, 0.2, -1.6] },
  { pos: [3.4, 4.4, 4.6], look: [-1.6, 0.45, -1.1] },
  { pos: [2.7, 3.5, 3.7], look: [-1.7, 0.55, -1.2] },
  { pos: [3.6, 3.1, 3.9], look: [-0.9, 0.25, -1.0] },
  { pos: [17, 15.5, 19], look: [0.3, 0, -1.3] },
];

function lerpKey(c: number, pos: THREE.Vector3, look: THREE.Vector3) {
  const i = Math.min(KEYS.length - 2, Math.max(0, Math.floor(c)));
  const t = ramp(c - i, 0, 1);
  const a = KEYS[i], b = KEYS[i + 1];
  pos.set(...a.pos).lerp(new THREE.Vector3(...b.pos), t);
  look.set(...a.look).lerp(new THREE.Vector3(...b.look), t);
}

function CameraRig({ progress, reduced }: { progress: MutableRefObject<number>; reduced: boolean }) {
  const { camera } = useThree();

  const pos = useMemo(() => new THREE.Vector3(), []);
  const look = useMemo(() => new THREE.Vector3(), []);
  const current = useRef(new THREE.Vector3(...KEYS[0].look));
  useFrame(() => {
    lerpKey(reduced ? 2 : progress.current, pos, look);      // reduced motion: one fixed, close view
    const k = reduced ? 1 : 0.08;
    camera.position.lerp(pos, k);
    current.current.lerp(look, k);
    camera.lookAt(current.current);
  });
  return null;
}

function Chip({ text, tone }: { text: string; tone: "vital" | "alert" }) {
  return (
    <div
      className={`whitespace-nowrap rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider ${
        tone === "alert" ? "border-alert bg-alert text-paper" : "border-line bg-paper text-ink"
      }`}
    >
      {text}
    </div>
  );
}

function Labels({ progress }: { progress: MutableRefObject<number> }) {
  const [stage, setStage] = useState(0);
  useFrame(() => {
    const c = progress.current;
    const s = c > 1.6 && c < 2.45 ? 1 : c >= 2.85 && c < 3.6 ? 2 : 0;
    if (s !== stage) setStage(s);
  });
  return (
    <>
      {stage === 1 && (
        <Html position={[FOCUS_X, 1.25, -1.0]} center zIndexRange={[10, 0]}>
          <Chip text="Lying in bed · normal" tone="vital" />
        </Html>
      )}
      {stage === 2 && (
        <Html position={[FOCUS_X + 1.2, 0.55, -0.9]} center zIndexRange={[10, 0]}>
          <Chip text="Potential fall · needs human review" tone="alert" />
        </Html>
      )}
    </>
  );
}

function Ward({ progress, reduced }: { progress: MutableRefObject<number>; reduced: boolean }) {
  const c = () => progress.current;
  // Story state, all derived from the chapter position.
  const occupied = () => c() >= 0.55 && c() < 3.85;
  const fall = () => ramp(c(), 2.35, 2.95) * (1 - ramp(c(), 3.55, 3.95));
  const statusOf = (x: number): (() => BedStatus) | BedStatus => {
    if (x === FOCUS_X) return () => (occupied() ? "occupied" : "free");
    if (x === BEDS_X[0]) return "occupied";
    if (x === BEDS_X[3]) return "cleaning";
    return "free";
  };

  return (
    <group>
      {/* floor slab and two low cut-away walls */}
      <mesh position={[0, -0.12, -0.6]} receiveShadow>
        <boxGeometry args={[14, 0.24, 8]} />
        <meshStandardMaterial color={C.slab} roughness={1} />
      </mesh>
      <mesh position={[0, 0.001, -0.6]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[13.6, 7.6]} />
        <meshStandardMaterial color={C.floor} roughness={1} />
      </mesh>
      <mesh position={[0, 0.8, -4.55]} receiveShadow castShadow>
        <boxGeometry args={[14, 1.6, 0.1]} />
        <meshStandardMaterial color={C.wall} roughness={1} />
      </mesh>
      <mesh position={[-6.95, 0.8, -0.6]} receiveShadow castShadow>
        <boxGeometry args={[0.1, 1.6, 8]} />
        <meshStandardMaterial color={C.wall} roughness={1} />
      </mesh>

      {BEDS_X.map((x) => (
        <Bed key={x} position={[x, 0, 0]} status={statusOf(x)} />
      ))}
      {/* the other occupied bed has a resting patient too */}
      <group position={[BEDS_X[0], 0, 0]}>
        <Skeleton fall={() => 0} alertTint={() => 0} />
      </group>

      <group position={[FOCUS_X, 0, 0]}>
        <group visible>
          <SkeletonWhenOccupied occupied={occupied} fall={fall} alert={() => (fall() > 0.9 ? 1 : 0)} />
        </group>
      </group>

      <WallCamera position={[FOCUS_X, 1.45, -4.35]} target={[FOCUS_X + 0.3, 0.2, -0.9]} on={() => ramp(c(), 1.35, 1.95)} />
      <QrCard position={[FOCUS_X + 1.05, 1.0, -0.2]} show={() => ramp(c(), 0.55, 0.95) * (1 - ramp(c(), 1.6, 1.95))} />
      <AlertRing position={[FOCUS_X + 1.2, 0.02, -0.9]} on={() => (fall() > 0.9 ? 1 : 0)} still={reduced} />
      <Labels progress={progress} />
    </group>
  );
}

function SkeletonWhenOccupied({ occupied, fall, alert }: { occupied: () => boolean; fall: () => number; alert: () => number }) {
  const g = useRef<THREE.Group>(null);
  useFrame(() => {
    if (g.current) g.current.visible = occupied();
  });
  return (
    <group ref={g}>
      <Skeleton fall={fall} alertTint={alert} />
    </group>
  );
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/** Static illustration shown when WebGL is unavailable. */
function Fallback() {
  return (
    <svg viewBox="0 0 600 400" className="h-full w-full" aria-hidden>
      <polygon points="60,250 300,130 540,250 300,370" fill={C.floor} stroke={C.slab} strokeWidth="2" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i} transform={`translate(${150 + i * 75}, ${215 + i * -37})`}>
          <polygon points="0,30 40,10 80,30 40,50" fill={C.mattress} stroke={C.bedFrame} strokeWidth="2" />
          <circle cx="62" cy="14" r="4" fill={i === 1 ? C.ink : C.vital} />
        </g>
      ))}
    </svg>
  );
}

export default function WardCanvas({ progress }: { progress: MutableRefObject<number> }) {
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const [reduced, setReduced] = useState(false);
  const [active, setActive] = useState(true);
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setWebgl(hasWebGL());
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onMq = () => setReduced(mq.matches);
    mq.addEventListener("change", onMq);
    // Stop rendering when the tab is hidden or the canvas is scrolled out of view.
    let visible = true, shown = !document.hidden;
    const update = () => setActive(visible && shown);
    const onVis = () => { shown = !document.hidden; update(); };
    document.addEventListener("visibilitychange", onVis);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; update(); });
    if (host.current) io.observe(host.current);
    return () => {
      mq.removeEventListener("change", onMq);
      document.removeEventListener("visibilitychange", onVis);
      io.disconnect();
    };
  }, []);

  return (
    <div ref={host} className="h-full w-full" aria-hidden>
      {webgl === false ? (
        <Fallback />
      ) : webgl ? (
        <Canvas
          shadows
          dpr={[1, 1.5]}
          frameloop={active ? "always" : "never"}
          camera={{ fov: 30, near: 0.1, far: 80, position: KEYS[0].pos }}
          gl={{ antialias: true, powerPreference: "high-performance" }}
          onCreated={({ gl }) => {
            gl.setClearColor(new THREE.Color("#f3efe6"), 0);
            gl.toneMapping = THREE.ACESFilmicToneMapping;
          }}
        >
          <ambientLight intensity={0.75} color="#fff7ea" />
          <directionalLight
            position={[6, 10, 5]}
            intensity={1.6}
            color="#fff1dc"
            castShadow
            shadow-mapSize={[1024, 1024]}
            shadow-camera-left={-9}
            shadow-camera-right={9}
            shadow-camera-top={7}
            shadow-camera-bottom={-7}
            shadow-bias={-0.0004}
          />
          <hemisphereLight args={["#fffaf0", "#d9d1c0", 0.35]} />
          <CameraRig progress={progress} reduced={reduced} />
          <Ward progress={progress} reduced={reduced} />
        </Canvas>
      ) : null}
    </div>
  );
}
