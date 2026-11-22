"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { C } from "./palette";

export type BedStatus = "free" | "occupied" | "cleaning";
const LIGHT: Record<BedStatus, string> = { free: C.vital, occupied: C.ink, cleaning: C.ochre };

/** A hospital bed, about 1 x 2.1 units, head toward -z. `status` may be a function read every frame. */
export function Bed({ position, status }: { position: [number, number, number]; status: BedStatus | (() => BedStatus) }) {
  const light = useRef<THREE.MeshStandardMaterial>(null);
  const target = new THREE.Color();

  useFrame(() => {
    if (!light.current) return;
    const s = typeof status === "function" ? status() : status;
    light.current.color.lerp(target.set(LIGHT[s]), 0.12);
  });

  return (
    <group position={position}>
      {/* frame and legs */}
      <mesh position={[0, 0.38, -1.05]} castShadow receiveShadow>
        <boxGeometry args={[1.0, 0.12, 2.1]} />
        <meshStandardMaterial color={C.bedFrame} roughness={0.9} />
      </mesh>
      {[[-0.44, -0.1], [0.44, -0.1], [-0.44, -2.0], [0.44, -2.0]].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.16, z]} castShadow>
          <cylinderGeometry args={[0.035, 0.035, 0.32, 10]} />
          <meshStandardMaterial color={C.inkMuted} roughness={0.6} />
        </mesh>
      ))}
      {/* mattress, sheet, pillow */}
      <mesh position={[0, 0.53, -1.05]} castShadow receiveShadow>
        <boxGeometry args={[0.94, 0.18, 2.02]} />
        <meshStandardMaterial color={C.mattress} roughness={1} />
      </mesh>
      <mesh position={[0, 0.625, -0.6]} receiveShadow>
        <boxGeometry args={[0.96, 0.02, 1.1]} />
        <meshStandardMaterial color={C.sheet} roughness={1} />
      </mesh>
      <mesh position={[0, 0.67, -1.8]} castShadow>
        <boxGeometry args={[0.6, 0.1, 0.32]} />
        <meshStandardMaterial color={C.pillow} roughness={1} />
      </mesh>
      {/* headboard with status light */}
      <mesh position={[0, 0.62, -2.12]} castShadow receiveShadow>
        <boxGeometry args={[1.04, 0.9, 0.06]} />
        <meshStandardMaterial color={C.bedFrame} roughness={0.85} />
      </mesh>
      <mesh position={[0.36, 1.1, -2.1]}>
        <sphereGeometry args={[0.055, 16, 16]} />
        <meshStandardMaterial ref={light} color={C.vital} roughness={0.4} />
      </mesh>
    </group>
  );
}
