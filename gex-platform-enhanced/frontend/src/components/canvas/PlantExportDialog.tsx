/**
 * PlantExportDialog — Export the plant canvas as PNG, PDF, or animated GIF.
 * The export layout: Header (title + date) → Diagram (tight-cropped) → Legend (beside diagram).
 * Nothing overlaps. Canvas size adapts to the actual plant design size.
 */
import { useState, useCallback } from "react";
import { getNodesBounds, getViewportForBounds, type Node } from "@xyflow/react";
import { toPng } from "html-to-image";
import jsPDF from "jspdf";
import { Download, FileImage, FileText, Film, Loader2 } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";

interface LegendItem { label: string; color: string }

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  plantName: string;
  companyName?: string;
  plantCapacity?: string;
  nodes: Node[];
  legendItems: LegendItem[];
}

const IMAGE_SCALE = 4;
const GIF_SCALE = 2;

// Title block height (CSS px — multiplied by scale at render)
const TITLE_BLOCK_H = 56;

export default function PlantExportDialog({ open, onOpenChange, plantName, companyName, plantCapacity, nodes, legendItems }: Props) {
  const [exporting, setExporting] = useState<"png" | "pdf" | "gif" | null>(null);

  const getCanvasElement = useCallback(() => {
    return document.querySelector(".react-flow__viewport") as HTMLElement | null;
  }, []);

  /** Hide edit UI and boost label sizes for export readability. */
  const hideEditUI = useCallback(() => {
    const el = getCanvasElement();
    if (!el) return () => {};
    const style = document.createElement('style');
    style.id = 'export-hide-edit-ui';
    style.textContent = `
      .react-flow__viewport [title^="Status:"],
      .react-flow__viewport [title^="Missing manufacturer"],
      .react-flow__viewport [title^="Manufacturer:"] {
        display: none !important;
      }
      .react-flow__viewport .group .absolute.-top-2,
      .react-flow__viewport .group .absolute.-top-3:not([class*="translate-x"]) {
        display: none !important;
      }
      /* Boost flow labels for readability at presentation scale */
      .react-flow__edgelabel-renderer .rounded-full {
        transform: scale(1.35) !important;
        font-weight: 700 !important;
      }
      /* Boost node labels */
      .react-flow__node .text-\\[10px\\],
      .react-flow__node .text-\\[11px\\] {
        font-size: 13px !important;
        font-weight: 600 !important;
      }
      .react-flow__node .text-xs {
        font-size: 14px !important;
      }
      .react-flow__node .text-sm {
        font-size: 15px !important;
        font-weight: 700 !important;
      }
    `;
    document.head.appendChild(style);
    return () => { style.remove(); };
  }, [getCanvasElement]);

  /** Capture the diagram viewport tightly — 1.5% padding, zoom to fill. */
  const captureImage = useCallback(async (scale = IMAGE_SCALE): Promise<{ dataUrl: string; w: number; h: number }> => {
    const restoreUI = hideEditUI();
    try {
      if (nodes.length === 0) throw new Error("No nodes available for export");
      // Wait a couple of frames so virtualization-off re-mounts every node
      // (offscreen gates/equipment) before we snapshot the viewport.
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      const bounds = getNodesBounds(nodes);
      // Generous padding so gate pills, edge labels, and flow animations
      // near the diagram edges aren't clipped during capture.
      const NODE_PAD = 120;
      const padX = Math.max(NODE_PAD, bounds.width * 0.04);
      const padY = Math.max(NODE_PAD, bounds.height * 0.04);
      const w = bounds.width + padX * 2;
      const h = bounds.height + padY * 2;
      const viewport = getViewportForBounds(bounds, w, h, 1, 2, Math.min(padX, padY));
      const el = getCanvasElement();
      if (!el) throw new Error("Canvas not found");
      const dataUrl = await toPng(el, {
        backgroundColor: "#f0f2f5",
        width: w, height: h,
        pixelRatio: scale,
        style: {
          width: `${w}px`, height: `${h}px`,
          transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
        },
      });
      return { dataUrl, w, h };
    } finally {
      restoreUI();
    }
  }, [nodes, getCanvasElement, hideEditUI]);

  /** Compose final image: title block (full width) → diagram (left) + legend (right, reserved column). */
  const composeFinal = useCallback(async (
    dataUrl: string, _dw: number, _dh: number, scale = IMAGE_SCALE,
  ): Promise<HTMLCanvasElement> => {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const s = scale;
        const titleH = TITLE_BLOCK_H * s;
        const sep = 2 * s;
        const gutter = 8 * s;
        const diagMargin = 6 * s; // thin margin around diagram
        const FILL_RATIO = 0.93; // diagram fills 93% of available area

        // ── Protected zone 1: Legend (right column) ──
        const resolvedLegendItems = legendItems;
        const legendPad = 10 * s;
        const itemH = 14 * s;
        const legendW = 120 * s;
        const legendContentH = resolvedLegendItems.length * itemH + legendPad * 2;

        // ── Canvas width: diagram area + gutter + legend ──
        const minCanvasW = Math.max(img.width, 1200 * s);
        const totalW = minCanvasW + gutter + legendW;

        // ── Available diagram region (excludes protected zones + thin margins) ──
        const diagAvailW = totalW - gutter - legendW - diagMargin * 2;
        // Use image aspect ratio to derive ideal body height, then clamp
        const idealBodyH = (img.height / img.width) * diagAvailW;
        const diagAvailH = Math.max(idealBodyH, legendContentH, 400 * s);

        // Aspect-ratio-preserving scale → fill 93% of available area
        const fitScale = Math.min(diagAvailW / img.width, diagAvailH / img.height) * FILL_RATIO;
        const scaledDiagW = Math.round(img.width * fitScale);
        const scaledDiagH = Math.round(img.height * fitScale);

        // Body height accommodates both diagram and legend
        const bodyH = Math.max(scaledDiagH + diagMargin * 2, legendContentH + diagMargin * 2);
        // Protected zone 2: Title block (top)
        const totalH = titleH + sep + bodyH;

        const c = document.createElement("canvas");
        c.width = totalW;
        c.height = totalH;
        const ctx = c.getContext("2d")!;

        // ── Background ──
        ctx.fillStyle = "#f0f2f5";
        ctx.fillRect(0, 0, totalW, totalH);

        // ── Title block — protected zone (full width, top) ──
        ctx.fillStyle = "#1e293b";
        ctx.fillRect(0, 0, totalW, titleH);
        ctx.fillStyle = "#3b82f6";
        ctx.fillRect(0, titleH, totalW, sep);

        const padX = 20 * s;
        const padY = 16 * s;
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${16 * s}px Inter,system-ui,sans-serif`;
        ctx.fillText(plantName, padX, padY + 14 * s);

        const subtitleParts: string[] = [];
        if (companyName) subtitleParts.push(companyName);
        if (plantCapacity) subtitleParts.push(plantCapacity);
        subtitleParts.push(new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }));
        ctx.fillStyle = "rgba(255,255,255,0.65)";
        ctx.font = `${10 * s}px Inter,system-ui,sans-serif`;
        ctx.fillText(subtitleParts.join("  ·  "), padX, padY + 32 * s);

        ctx.font = `600 ${9 * s}px Inter,system-ui,sans-serif`;
        const badgeText = "Plant Design Export";
        const badgeW = ctx.measureText(badgeText).width + 16 * s;
        const badgeH = 18 * s;
        const badgeX = totalW - padX - badgeW;
        const badgeY = titleH / 2 - badgeH / 2;
        ctx.fillStyle = "rgba(255,255,255,0.12)";
        ctx.beginPath(); ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 4 * s); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.7)";
        ctx.fillText(badgeText, badgeX + 8 * s, badgeY + 12 * s);

        // ── Diagram — constrained to available region, centered ──
        const bodyTop = titleH + sep;
        const diagX = diagMargin + (diagAvailW - scaledDiagW) / 2;
        const diagY = bodyTop + (bodyH - scaledDiagH) / 2;
        ctx.drawImage(img, diagX, diagY, scaledDiagW, scaledDiagH);

        // ── Legend (right side, vertically centered, no container) ──
        const legX = totalW - legendW;
        const legY = bodyTop + (bodyH - legendContentH) / 2;

        resolvedLegendItems.forEach((item, i) => {
          const iy = legY + legendPad + i * itemH;
          // Color dot
          ctx.fillStyle = item.color;
          ctx.beginPath();
          ctx.arc(legX + legendPad + 4 * s, iy + 5 * s, 4 * s, 0, Math.PI * 2);
          ctx.fill();
          // Label
          ctx.fillStyle = "#475569";
          ctx.font = `500 ${8 * s}px Inter,system-ui,sans-serif`;
          ctx.fillText(item.label, legX + legendPad + 14 * s, iy + 8 * s);
        });

        resolve(c);
      };
      img.src = dataUrl;
    });
  }, [plantName, companyName, plantCapacity, legendItems]);

  // ── Export handlers ──

  const handleExportPNG = useCallback(async () => {
    console.log('[ExportPNG] Legend items:', legendItems.map(i => `${i.label}(${i.color})`));
    console.log('[ExportPNG] Nodes count:', nodes.length);
    setExporting("png");
    try {
      const { dataUrl, w, h } = await captureImage();
      const canvas = await composeFinal(dataUrl, w, h);
      const blob = await new Promise<Blob>((r) => canvas.toBlob((b) => r(b!), "image/png"));
      const url = URL.createObjectURL(blob);
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const a = document.createElement("a"); a.href = url;
      a.download = `${plantName.replace(/\s+/g, "-").toLowerCase()}-plant-design-${ts}.png`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e) { console.error("PNG export failed:", e); }
    finally { setExporting(null); }
  }, [captureImage, composeFinal, plantName]);

  const handleExportPDF = useCallback(async () => {
    setExporting("pdf");
    try {
      const { dataUrl, w, h } = await captureImage();
      const canvas = await composeFinal(dataUrl, w, h);
      const imgData = canvas.toDataURL("image/png", 1.0);
      const imgW = canvas.width / IMAGE_SCALE, imgH = canvas.height / IMAGE_SCALE;
      const isLarge = imgW > 1200;
      const pdf = new jsPDF({ orientation: "landscape", unit: "pt", format: isLarge ? "a3" : "a4" });
      const pageW = pdf.internal.pageSize.getWidth(), pageH = pdf.internal.pageSize.getHeight();
      const m = 24, aW = pageW - m * 2, aH = pageH - m * 2;
      const s = Math.min(aW / imgW, aH / imgH);
      pdf.addImage(imgData, "PNG", m + (aW - imgW * s) / 2, m + (aH - imgH * s) / 2, imgW * s, imgH * s);
      const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      pdf.save(`${plantName.replace(/\s+/g, "-").toLowerCase()}-plant-design-${ts}.pdf`);
    } catch (e) { console.error("PDF export failed:", e); }
    finally { setExporting(null); }
  }, [captureImage, composeFinal, plantName]);

  const handleExportGIF = useCallback(async () => {
    setExporting("gif");
    try {
      const frameCount = 20;
      const delay = 120;
      const frames: HTMLCanvasElement[] = [];
      for (let i = 0; i < frameCount; i++) {
        const { dataUrl, w, h } = await captureImage(GIF_SCALE);
        const canvas = await composeFinal(dataUrl, w, h, GIF_SCALE);
        frames.push(canvas);
        await new Promise((r) => setTimeout(r, delay));
      }
      if (frames.length === 0) throw new Error("No frames captured");
      const fw = frames[0].width, fh = frames[0].height;
      const gif = await buildGif(frames, fw, fh, delay);
      const url = URL.createObjectURL(gif);
      const a = document.createElement("a"); a.href = url;
      a.download = `${plantName.replace(/\s+/g, "-").toLowerCase()}-plant-design.gif`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e) { console.error("GIF export failed:", e); }
    finally { setExporting(null); }
  }, [captureImage, composeFinal, plantName]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5 text-primary" />
            Export Plant Design
          </DialogTitle>
          <DialogDescription>
            Export your plant design as an image, document, or animation.
          </DialogDescription>
        </DialogHeader>

        {/* Live legend preview, exactly what will appear in the exported file */}
        {legendItems.length > 0 && (
          <div className="mt-2 rounded-lg border border-border bg-muted/30 p-2">
            <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1.5">Stream Colors in export</p>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {legendItems.map((item) => (
                <span key={item.label} className="flex items-center gap-1.5 text-[11px] text-foreground">
                  <span className="w-3 h-2 rounded-sm shrink-0" style={{ backgroundColor: item.color }} />
                  {item.label}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-3 gap-3 mt-2">
          <button onClick={handleExportPNG} disabled={!!exporting}
            className="flex flex-col items-center gap-3 rounded-lg border-2 border-border p-4 transition-all hover:border-primary/50 hover:bg-accent/50 disabled:opacity-50">
            {exporting === "png" ? <Loader2 className="h-7 w-7 text-primary animate-spin" /> : <FileImage className="h-7 w-7 text-primary" />}
            <div className="text-center">
              <p className="text-sm font-semibold text-foreground">PNG</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">High resolution</p>
            </div>
          </button>
          <button onClick={handleExportPDF} disabled={!!exporting}
            className="flex flex-col items-center gap-3 rounded-lg border-2 border-border p-4 transition-all hover:border-primary/50 hover:bg-accent/50 disabled:opacity-50">
            {exporting === "pdf" ? <Loader2 className="h-7 w-7 text-primary animate-spin" /> : <FileText className="h-7 w-7 text-primary" />}
            <div className="text-center">
              <p className="text-sm font-semibold text-foreground">PDF</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">Print-ready</p>
            </div>
          </button>
          <button onClick={handleExportGIF} disabled={!!exporting}
            className="flex flex-col items-center gap-3 rounded-lg border-2 border-border p-4 transition-all hover:border-primary/50 hover:bg-accent/50 disabled:opacity-50">
            {exporting === "gif" ? <Loader2 className="h-7 w-7 text-primary animate-spin" /> : <Film className="h-7 w-7 text-primary" />}
            <div className="text-center">
              <p className="text-sm font-semibold text-foreground">GIF</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">Animated flows</p>
            </div>
          </button>
        </div>

        <div className="mt-3 rounded-lg border border-border bg-muted/30 p-3">
          <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-2">Included in export</p>
          <ul className="space-y-1">
            {["System boundary & all gates", "Equipment with specifications", "Carriers with stream types", "Flow values on all connections", "Stream color legend (separate panel)", "Flow animations (GIF only)"].map((item) => (
              <li key={item} className="text-xs text-foreground flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-primary" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ═══════════════════════════════════════════════════════════
   Minimal GIF89a Encoder (no external dependency)
   ═══════════════════════════════════════════════════════════ */

async function buildGif(frames: HTMLCanvasElement[], width: number, height: number, delay: number): Promise<Blob> {
  const encoder = new GifEncoder(width, height);
  for (const frame of frames) {
    const ctx = frame.getContext("2d")!;
    const imageData = ctx.getImageData(0, 0, width, height);
    encoder.addFrame(imageData.data, delay);
  }
  return encoder.finish();
}

class GifEncoder {
  private width: number;
  private height: number;
  private frames: { data: Uint8ClampedArray; delay: number }[] = [];
  constructor(w: number, h: number) { this.width = w; this.height = h; }
  addFrame(rgba: Uint8ClampedArray, delay: number) { this.frames.push({ data: rgba, delay }); }

  finish(): Blob {
    const { width: w, height: h, frames } = this;
    const out: number[] = [];
    const palette = this.buildPalette(frames[0].data);
    this.writeStr(out, "GIF89a");
    this.writeU16(out, w); this.writeU16(out, h);
    out.push(0xf7, 0, 0);
    for (let i = 0; i < 256; i++) out.push(palette[i*3], palette[i*3+1], palette[i*3+2]);
    out.push(0x21, 0xff, 0x0b);
    this.writeStr(out, "NETSCAPE2.0");
    out.push(0x03, 0x01); this.writeU16(out, 0); out.push(0x00);
    for (const frame of frames) {
      out.push(0x21, 0xf9, 0x04, 0x00);
      this.writeU16(out, Math.round(frame.delay / 10));
      out.push(0x00, 0x00, 0x2c);
      this.writeU16(out, 0); this.writeU16(out, 0);
      this.writeU16(out, w); this.writeU16(out, h);
      out.push(0x00);
      const indexed = this.quantize(frame.data, palette);
      const compressed = this.lzwEncode(indexed, 8);
      out.push(8);
      let pos = 0;
      while (pos < compressed.length) {
        const chunk = Math.min(255, compressed.length - pos);
        out.push(chunk);
        for (let i = 0; i < chunk; i++) out.push(compressed[pos++]);
      }
      out.push(0x00);
    }
    out.push(0x3b);
    return new Blob([new Uint8Array(out)], { type: "image/gif" });
  }

  private buildPalette(rgba: Uint8ClampedArray): Uint8Array {
    const counts = new Map<number, number>();
    const step = Math.max(1, Math.floor(rgba.length / 4 / 10000));
    for (let i = 0; i < rgba.length; i += 4 * step) {
      const key = ((rgba[i] & 0xfc) << 16) | ((rgba[i+1] & 0xfc) << 8) | (rgba[i+2] & 0xfc);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 256);
    const p = new Uint8Array(256 * 3);
    for (let i = 0; i < sorted.length; i++) {
      p[i*3] = (sorted[i][0] >> 16) & 0xff;
      p[i*3+1] = (sorted[i][0] >> 8) & 0xff;
      p[i*3+2] = sorted[i][0] & 0xff;
    }
    return p;
  }

  private quantize(rgba: Uint8ClampedArray, palette: Uint8Array): Uint8Array {
    const pixels = this.width * this.height;
    const indexed = new Uint8Array(pixels);
    const cache = new Map<number, number>();
    for (let i = 0; i < pixels; i++) {
      const ri = i * 4;
      const key = ((rgba[ri] & 0xfc) << 16) | ((rgba[ri+1] & 0xfc) << 8) | (rgba[ri+2] & 0xfc);
      if (cache.has(key)) { indexed[i] = cache.get(key)!; continue; }
      let best = 0, bestD = Infinity;
      for (let j = 0; j < 256; j++) {
        const dr = (rgba[ri] & 0xfc) - palette[j*3];
        const dg = (rgba[ri+1] & 0xfc) - palette[j*3+1];
        const db = (rgba[ri+2] & 0xfc) - palette[j*3+2];
        const d = dr*dr + dg*dg + db*db;
        if (d < bestD) { bestD = d; best = j; }
        if (d === 0) break;
      }
      cache.set(key, best); indexed[i] = best;
    }
    return indexed;
  }

  private lzwEncode(indexed: Uint8Array, minCodeSize: number): number[] {
    const clearCode = 1 << minCodeSize;
    const eoiCode = clearCode + 1;
    let codeSize = minCodeSize + 1;
    let nextCode = eoiCode + 1;
    let table = new Map<string, number>();
    for (let i = 0; i < clearCode; i++) table.set(String(i), i);
    const output: number[] = [];
    let buffer = 0, bufferBits = 0;
    const emit = (code: number) => {
      buffer |= code << bufferBits; bufferBits += codeSize;
      while (bufferBits >= 8) { output.push(buffer & 0xff); buffer >>= 8; bufferBits -= 8; }
    };
    emit(clearCode);
    let prefix = String(indexed[0]);
    for (let i = 1; i < indexed.length; i++) {
      const suffix = String(indexed[i]);
      const combined = prefix + "," + suffix;
      if (table.has(combined)) { prefix = combined; }
      else {
        emit(table.get(prefix)!);
        if (nextCode < 4096) {
          table.set(combined, nextCode++);
          if (nextCode > (1 << codeSize) && codeSize < 12) codeSize++;
        } else {
          emit(clearCode); table = new Map();
          for (let j = 0; j < clearCode; j++) table.set(String(j), j);
          nextCode = eoiCode + 1; codeSize = minCodeSize + 1;
        }
        prefix = suffix;
      }
    }
    emit(table.get(prefix)!); emit(eoiCode);
    if (bufferBits > 0) output.push(buffer & 0xff);
    return output;
  }

  private writeStr(out: number[], s: string) { for (let i = 0; i < s.length; i++) out.push(s.charCodeAt(i)); }
  private writeU16(out: number[], v: number) { out.push(v & 0xff, (v >> 8) & 0xff); }
}
