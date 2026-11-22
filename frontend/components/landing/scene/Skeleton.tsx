"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { C } from "./palette";

// The 17 COCO keypoints the pose model tracks, in bed-local coordinates (bed head toward -z).
type P = [number, number, number];
// Lying on the back in bed.
const IN_BED: P[] = [
  [0, 0.78, -1.82], [0.04, 0.8, -1.85], [-0.04, 0.8, -1.85], [0.08, 0.75, -1.88], [-0.08, 0.75, -1.88],
  [0.19, 0.71, -1.6], [-0.19, 0.71, -1.6], [0.27, 0.69, -1.33], [-0.27, 0.69, -1.33], [0.25, 0.71, -1.07], [-0.25, 0.71, -1.07],
  [0.11, 0.71, -1.1], [-0.11, 0.71, -1.1], [0.12, 0.72, -0.66], [-0.12, 0.72, -0.66], [0.12, 0.71, -0.24], [-0.12, 0.71, -0.24],
];
// Crumpled on the floor beside the bed.
const ON_FLOOR: P[] = [
  [1.15, 0.14, -1.55], [1.12, 0.17, -1.58], [1.18, 0.17, -1.57], [1.08, 0.12, -1.6], [1.21, 0.12, -1.6],
  [1.0, 0.12, -1.32], [1.3, 0.15, -1.36], [0.84, 0.08, -1.1], [1.47, 0.1, -1.55], [0.9, 0.06, -0.85], [1.62, 0.06, -1.76],
  [1.05, 0.12, -0.82], [1.28, 0.14, -0.86], [1.36, 0.1, -0.5], [1.1, 0.1, -0.42], [1.2, 0.06, -0.12], [1.46, 0.06, -0.15],
];
const LIMBS: [number, number][] = [
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [0, 5], [0, 6],
];

const up = new THREE.Vector3(0, 1, 0);

/** Pose skeleton that blends from lying in bed (0) to lying on the floor (1). `fall` is read every frame. */
export function Skeleton({ fall, alertTint }: { fall: () => number; alertTint: () => number }) {
  const joints = useRef<(THREE.Mesh | null)[]>([]);
  const limbs = useRef<(THREE.Mesh | null)[]>([]);
  const jointMat = useMemo(() => new THREE.MeshStandardMaterial({ color: C.joint, roughness: 0.5 }), []);
  const limbMat = useMemo(() => new THREE.MeshStandardMaterial({ color: C.vital, roughness: 0.6 }), []);
  const pts = useMemo(() => IN_BED.map(() => new THREE.Vector3()), []);
  const tmp = useMemo(() => ({ a: new THREE.Vector3(), b: new THREE.Vector3(), mid: new THREE.Vector3(), dir: new THREE.Vector3(), c: new THREE.Color() }), []);

  useFrame(() => {
    const t = fall();
    const arc = Math.sin(Math.PI * t) * 0.35;              // the body rises off the bed edge, then drops
    for (let i = 0; i < 17; i++) {
      const a = IN_BED[i], b = ON_FLOOR[i];
      pts[i].set(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t + arc, a[2] + (b[2] - a[2]) * t);
      joints.current[i]?.position.copy(pts[i]);
    }
    LIMBS.forEach(([i, j], k) => {
      const m = limbs.current[k];
      if (!m) return;
      tmp.dir.subVectors(pts[j], pts[i]);
      const len = tmp.dir.length();
      m.position.copy(tmp.mid.addVectors(pts[i], pts[j]).multiplyScalar(0.5));
      m.scale.set(1, Math.max(len, 0.001), 1);
      m.quaternion.setFromUnitVectors(up, tmp.dir.normalize());
    });
    limbMat.color.lerp(tmp.c.set(alertTint() > 0.5 ? C.alert : C.vital), 0.15);
  });

  return (
    <group>
      {IN_BED.map((_, i) => (
        <mesh key={i} ref={(m) => { joints.current[i] = m; }} material={jointMat} castShadow>
          <sphereGeometry args={[i < 5 ? 0.028 : 0.04, 12, 12]} />
        </mesh>
      ))}
      {LIMBS.map((_, k) => (
        <mesh key={k} ref={(m) => { limbs.current[k] = m; }} material={limbMat} castShadow>
          <cylinderGeometry args={[0.018, 0.018, 1, 8]} />
        </mesh>
      ))}
    </group>
  );
}
