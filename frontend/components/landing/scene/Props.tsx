"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { C } from "./palette";

/** Wall camera with a translucent view cone pointing at the bed. `on` is 0..1, read every frame. */
export function WallCamera({ position, target, on }: { position: [number, number, number]; target: [number, number, number]; on: () => number }) {
  const cone = useRef<THREE.Mesh>(null);
  const mat = useMemo(() => new THREE.MeshBasicMaterial({ color: C.vital, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }), []);
  const { mid, quat, len } = useMemo(() => {
    const a = new THREE.Vector3(...position), b = new THREE.Vector3(...target);
    const dir = new THREE.Vector3().subVectors(b, a);
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, -1, 0), dir.clone().normalize());
    return { mid: a.clone().add(b).multiplyScalar(0.5), quat: q, len: dir.length() };
  }, [position, target]);

  useFrame(() => {
    const v = on();
    mat.opacity = 0.09 * v;
    if (cone.current) cone.current.visible = v > 0.01;
  });

  return (
    <group>
      <group position={position} quaternion={quat}>
        <mesh castShadow>
          <boxGeometry args={[0.22, 0.16, 0.3]} />
          <meshStandardMaterial color={C.ink} roughness={0.5} />
        </mesh>
        <mesh position={[0, -0.1, 0]} rotation={[0, 0, 0]}>
          <cylinderGeometry args={[0.05, 0.06, 0.08, 16]} />
          <meshStandardMaterial color={C.inkMuted} roughness={0.3} />
        </mesh>
      </group>
      <mesh ref={cone} position={mid} quaternion={quat} material={mat}>
        <coneGeometry args={[0.8, len, 32, 1, true]} />
      </mesh>
    </group>
  );
}

/** Small QR card (procedural pattern) that floats above the bed while the patient is admitted. */
export function QrCard({ position, show }: { position: [number, number, number]; show: () => number }) {
  const group = useRef<THREE.Group>(null);
  const texture = useMemo(() => {
    const n = 21, px = 6, canvas = document.createElement("canvas");
    canvas.width = canvas.height = n * px;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = C.mattress;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = C.ink;
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const finder = (x: number, y: number) => {
      ctx.fillRect(x * px, y * px, 7 * px, 7 * px);
      ctx.clearRect((x + 1) * px, (y + 1) * px, 5 * px, 5 * px);
      ctx.fillStyle = C.mattress; ctx.fillRect((x + 1) * px, (y + 1) * px, 5 * px, 5 * px);
      ctx.fillStyle = C.ink; ctx.fillRect((x + 2) * px, (y + 2) * px, 3 * px, 3 * px);
    };
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (rnd() > 0.55) ctx.fillRect(x * px, y * px, px, px);
    finder(0, 0); finder(n - 7, 0); finder(0, n - 7);
    const t = new THREE.CanvasTexture(canvas);
    t.magFilter = THREE.NearestFilter;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);

  useFrame((state) => {
    const g = group.current;
    if (!g) return;
    const v = show();
    g.visible = v > 0.01;
    g.scale.setScalar(0.001 + 0.8 * v);
    g.position.y = position[1] + Math.sin(state.clock.elapsedTime * 1.2) * 0.03;
  });

  return (
    <group ref={group} position={position}>
      <mesh castShadow>
        <boxGeometry args={[0.5, 0.62, 0.02]} />
        <meshStandardMaterial color={C.mattress} roughness={0.9} />
      </mesh>
      <mesh position={[0, 0.05, 0.012]}>
        <planeGeometry args={[0.4, 0.4]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      <mesh position={[0, -0.23, 0.012]}>
        <planeGeometry args={[0.3, 0.035]} />
        <meshBasicMaterial color={C.vital} toneMapped={false} />
      </mesh>
    </group>
  );
}

/** Pulsing red ring on the floor under a potential fall. `on` is 0..1; `still` disables the pulse. */
export function AlertRing({ position, on, still }: { position: [number, number, number]; on: () => number; still: boolean }) {
  const ring = useRef<THREE.Mesh>(null);
  const mat = useMemo(() => new THREE.MeshBasicMaterial({ color: C.alert, transparent: true, opacity: 0, depthWrite: false }), []);
  useFrame((state) => {
    const v = on();
    const r = ring.current;
    if (!r) return;
    r.visible = v > 0.01;
    const phase = still ? 0.5 : (state.clock.elapsedTime * 0.8) % 1;
    r.scale.setScalar(0.8 + phase * 0.7);
    mat.opacity = v * (still ? 0.55 : 0.7 * (1 - phase));
  });
  return (
    <mesh ref={ring} position={position} rotation={[-Math.PI / 2, 0, 0]} material={mat}>
      <ringGeometry args={[0.55, 0.64, 48]} />
    </mesh>
  );
}
