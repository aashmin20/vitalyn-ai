// 3D colours, kept in step with the CSS tokens in app/globals.css (no gradients, no neon).
export const C = {
  floor: "#e7e1d3",
  slab: "#d9d1c0",
  wall: "#efeadf",
  bedFrame: "#cfc6b4",
  mattress: "#fbf9f4",
  sheet: "#e9e4d8",
  pillow: "#ffffff",
  ink: "#1b1a17",
  inkMuted: "#6b675e",
  vital: "#2e5b4f",
  alert: "#b4372b",
  ochre: "#b8893a",
  joint: "#1b1a17",
};

/** Clamp to 0..1 */
export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
/** 0 before a, 1 after b, smooth in between */
export const ramp = (v: number, a: number, b: number) => {
  const t = clamp01((v - a) / (b - a));
  return t * t * (3 - 2 * t);
};
