"use client";

import { useEffect, useRef, type RefObject } from "react";

/**
 * Continuous story position for the 3D scene: 0 at the first chapter, 1 at the second, and so on.
 * Each anchor is the scroll offset at which that chapter's section is centred in the viewport.
 * Kept in a ref (not React state) so scrolling never re-renders the page; the scene reads it per frame.
 */
export function useChapterProgress(container: RefObject<HTMLElement>, sections: RefObject<HTMLElement>[]) {
  const progress = useRef(0);

  useEffect(() => {
    const el = container.current;
    if (!el) return;
    let frame = 0;

    const measure = () => {
      frame = 0;
      const vh = el.clientHeight;
      const anchors = sections
        .map((s) => s.current)
        .filter((s): s is HTMLElement => !!s)
        .map((s) => s.offsetTop + s.offsetHeight / 2 - vh / 2);
      if (anchors.length === 0) return;
      const y = el.scrollTop;
      if (y <= anchors[0]) progress.current = 0;
      else if (y >= anchors[anchors.length - 1]) progress.current = anchors.length - 1;
      else {
        const i = anchors.findIndex((a, k) => y >= a && y < anchors[k + 1]);
        progress.current = i + (y - anchors[i]) / Math.max(1, anchors[i + 1] - anchors[i]);
      }
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    el.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [container, sections]);

  return progress;
}
