let ctx: AudioContext | null = null;

/** Call from a user gesture (e.g. the Start button) so the browser allows audio later. */
export function primeAlertSound(): void {
  try {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    ctx = ctx ?? new AC();
    void ctx.resume();
  } catch {
    // audio unavailable; the visual alarm still shows
  }
}

/** Three short two-tone beeps. No-op if audio was never primed or is blocked. */
export function playAlertSound(): void {
  try {
    if (!ctx || ctx.state !== "running") return;
    const now = ctx.currentTime;
    for (let i = 0; i < 3; i++) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = i % 2 === 0 ? 880 : 660;
      gain.gain.setValueAtTime(0.0001, now + i * 0.35);
      gain.gain.exponentialRampToValueAtTime(0.25, now + i * 0.35 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.35 + 0.28);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + i * 0.35);
      osc.stop(now + i * 0.35 + 0.3);
    }
  } catch {
    // ignore
  }
}
