// Generative hero background — particle depth, orbital rings, dashed arcs.
//
// Replaces the radial-gradient CSS glow that made the old hero read as a
// generated template. This is the greenearthx.com visual register (depth
// gradient, drifting particles, concentric rings) drawn in canvas rather than
// shipped as a raster: ~4KB instead of ~1MB, redraws at any size, recolours
// from props, and cannot be watermarked. The glass orb and butterfly on the
// public site are the genuinely photographic parts — those are not reproduced
// here and would need licensing or a commission.
//
// Behaviour: paints its first frame synchronously on mount so the hero is
// never blank; pauses when the tab is hidden; honours prefers-reduced-motion
// by drawing one static frame and never starting the loop.
import { useEffect, useRef } from 'react';

export type HeroPalette = 'ocean' | 'forest' | 'graphite';

const PALETTES: Record<HeroPalette, {
  a: string; b: string; c: string; glow: string;
  dot: string; ring: string; node: string;
}> = {
  ocean:    { a: '#04182B', b: '#0A3A4A', c: '#0C5348', glow: '#12796B',
              dot: '#A8DCE8', ring: '#3FBFA8', node: '#7FE3CC' },
  forest:   { a: '#061410', b: '#0B2A1D', c: '#114430', glow: '#17654A',
              dot: '#B6E6C8', ring: '#4FD0A0', node: '#8CF0C4' },
  graphite: { a: '#0B0D0F', b: '#12181A', c: '#17231F', glow: '#1E3B34',
              dot: '#C3CEC8', ring: '#3FBFA8', node: '#7FE3CC' },
};

type Particle = { x: number; y: number; r: number; a: number;
                  vx: number; vy: number; tw: number };
type Ring = { rad: number; w: number; a: number; dash: boolean;
              sp: number; ph: number; nodes: number };

export function HeroField({ palette = 'ocean' }: { palette?: HeroPalette }) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const pal = PALETTES[palette] ?? PALETTES.ocean;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let W = 0, H = 0, t = 0;
    let raf: number | null = null;
    let parts: Particle[] = [];
    let rings: Ring[] = [];

    const seed = () => {
      parts = [];
      const n = Math.round(Math.min(260, (W * H) / 5200));
      for (let i = 0; i < n; i++) {
        const d = Math.random();                    // depth → size + parallax
        parts.push({
          x: Math.random() * W, y: Math.random() * H,
          r: 0.5 + d * 1.7, a: 0.16 + d * 0.55,
          vx: (Math.random() - 0.5) * 0.055 * (0.4 + d),
          vy: (Math.random() - 0.5) * 0.055 * (0.4 + d),
          tw: Math.random() * Math.PI * 2,
        });
      }
      rings = [];
      for (let j = 0; j < 7; j++) {
        rings.push({
          rad: 0.10 + j * 0.085, w: j % 3 === 0 ? 1.1 : 0.7,
          a: 0.30 - j * 0.028, dash: j % 2 === 1,
          sp: (j % 2 ? 1 : -1) * (0.00016 + j * 0.00006),
          ph: Math.random() * Math.PI * 2, nodes: 1 + (j % 3),
        });
      }
    };

    const draw = () => {
      const g = ctx.createLinearGradient(W, 0, 0, H);
      g.addColorStop(0, pal.a); g.addColorStop(0.52, pal.b); g.addColorStop(1, pal.c);
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

      // focal glow, right of centre — mirrors the .com composition
      const fx = W * 0.70, fy = H * 0.44, R = Math.max(W, H) * 0.52;
      const rg = ctx.createRadialGradient(fx, fy, 0, fx, fy, R);
      rg.addColorStop(0, pal.glow); rg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.globalAlpha = 0.55; ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
      ctx.globalAlpha = 1;

      const base = Math.min(W, H);
      for (const r of rings) {
        const rad = r.rad * base * 1.55;
        ctx.save(); ctx.translate(fx, fy); ctx.rotate(r.ph + t * r.sp * 60);
        ctx.beginPath(); ctx.arc(0, 0, rad, 0, Math.PI * 2);
        ctx.strokeStyle = pal.ring; ctx.globalAlpha = r.a; ctx.lineWidth = r.w;
        ctx.setLineDash(r.dash ? [1.5, 7] : []);
        ctx.stroke(); ctx.setLineDash([]);
        for (let k = 0; k < r.nodes; k++) {
          const ang = (Math.PI * 2 / r.nodes) * k;
          ctx.beginPath();
          ctx.arc(Math.cos(ang) * rad, Math.sin(ang) * rad, 1.9, 0, Math.PI * 2);
          ctx.fillStyle = pal.node; ctx.globalAlpha = r.a * 2.1; ctx.fill();
        }
        ctx.restore();
      }
      ctx.globalAlpha = 1;

      for (const p of parts) {
        const tw = reduce ? 1 : 0.72 + 0.28 * Math.sin(t * 0.9 + p.tw);
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = pal.dot; ctx.globalAlpha = p.a * tw; ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas.clientWidth; H = canvas.clientHeight;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed(); draw();
    };

    const step = () => {
      t += 0.016;
      for (const p of parts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < -4) p.x = W + 4; if (p.x > W + 4) p.x = -4;
        if (p.y < -4) p.y = H + 4; if (p.y > H + 4) p.y = -4;
      }
      draw();
      raf = requestAnimationFrame(step);
    };
    const start = () => { if (raf === null && !reduce) raf = requestAnimationFrame(step); };
    const stop = () => { if (raf !== null) { cancelAnimationFrame(raf); raf = null; } };
    const onVis = () => { if (document.hidden) stop(); else start(); };

    resize();                       // first frame is painted before anything animates
    start();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', onVis);

    return () => {
      stop();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [palette]);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="absolute inset-0 w-full h-full block"
    />
  );
}

export default HeroField;
