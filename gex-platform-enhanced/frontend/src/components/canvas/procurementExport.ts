/**
 * Procurement Export — generates CSV and PDF downloads
 * from procurement comparison data.
 */
import type { Node } from "@xyflow/react";
import {
  type ProcurementStrategy,
  type EquipmentProcurement,
  getProcurementEntry,
  strategyLabels,
} from "./procurementDatabase";

export interface ProcurementLineItem {
  equipment: string;
  strategy: ProcurementStrategy;
  manufacturer: string;
  model: string;
  country: string;
  /** Unit price */
  priceEur: number;
  /** Total scaled price for the plant (priceEur × plantScaleQty) */
  scaledPriceEur: number;
  priceDisplay: string;
  efficiency: string;
  leadTimeMonths: number;
  trl: number;
  scaleThreshold?: string;
  plantScaleQty: number;
}

export interface ProcurementReport {
  plantName: string;
  generatedAt: string;
  strategy: ProcurementStrategy;
  lineItems: ProcurementLineItem[];
  totalCapexEur: number;
}

export function buildProcurementReport(
  nodes: Node[],
  strategy: ProcurementStrategy,
  plantName: string
): ProcurementReport {
  const lineItems: ProcurementLineItem[] = [];
  let total = 0;

  for (const node of nodes) {
    if (node.type !== "equipment") continue;
    const entry = getProcurementEntry(node.data.label as string);
    if (!entry) continue;
    const opt = entry[strategy];
    const qty = entry.plantScaleQty ?? 1;
    const scaledPrice = opt.priceEur * qty;
    total += scaledPrice;
    lineItems.push({
      equipment: node.data.label as string,
      strategy,
      manufacturer: opt.manufacturer,
      model: opt.model,
      country: opt.country,
      priceEur: opt.priceEur,
      scaledPriceEur: scaledPrice,
      priceDisplay: opt.priceDisplay,
      efficiency: opt.efficiency,
      leadTimeMonths: opt.leadTimeMonths,
      trl: opt.trl,
      scaleThreshold: opt.scaleThreshold,
      plantScaleQty: qty,
    });
  }

  return {
    plantName,
    generatedAt: new Date().toISOString(),
    strategy,
    lineItems,
    totalCapexEur: total,
  };
}

/** Build a full comparison report with all 3 strategies */
export function buildComparisonReport(
  nodes: Node[],
  plantName: string
): { strategies: Record<ProcurementStrategy, ProcurementReport>; equipmentEntries: { label: string; entry: EquipmentProcurement }[] } {
  const allStrategies: ProcurementStrategy[] = ["bestPrice", "bestEfficiency", "economiesOfScale"];
  const strategies = {} as Record<ProcurementStrategy, ProcurementReport>;
  for (const s of allStrategies) {
    strategies[s] = buildProcurementReport(nodes, s, plantName);
  }

  const equipmentEntries: { label: string; entry: EquipmentProcurement }[] = [];
  for (const node of nodes) {
    if (node.type !== "equipment") continue;
    const entry = getProcurementEntry(node.data.label as string);
    if (entry) equipmentEntries.push({ label: node.data.label as string, entry });
  }

  return { strategies, equipmentEntries };
}

/* ═══════════════════════════ CSV EXPORT ═══════════════════════════ */

export function downloadCSV(nodes: Node[], plantName: string) {
  const { strategies, equipmentEntries } = buildComparisonReport(nodes, plantName);
  const allStrategies: ProcurementStrategy[] = ["bestPrice", "bestEfficiency", "economiesOfScale"];

  const rows: string[] = [];
  rows.push(`Procurement Comparison Report, ${plantName}`);
  rows.push(`Generated: ${new Date().toLocaleString()}`);
  rows.push("");

  // Header
  rows.push([
    "Equipment",
    ...allStrategies.flatMap((s) => [
      `${strategyLabels[s].label}, Manufacturer`,
      `${strategyLabels[s].label}, Model`,
      `${strategyLabels[s].label}, Country`,
      `${strategyLabels[s].label}, Price`,
      `${strategyLabels[s].label}, Price (EUR)`,
      `${strategyLabels[s].label}, Efficiency`,
      `${strategyLabels[s].label}, Lead Time (mo)`,
      `${strategyLabels[s].label}, TRL`,
    ]),
  ].join(","));

  // Data rows
  for (const { label, entry } of equipmentEntries) {
    const cols = [
      `"${label}"`,
      ...allStrategies.flatMap((s) => {
        const opt = entry[s];
        return [
          `"${opt.manufacturer}"`,
          `"${opt.model}"`,
          `"${opt.country}"`,
          `"${opt.priceDisplay}"`,
          String(opt.priceEur),
          `"${opt.efficiency}"`,
          String(opt.leadTimeMonths),
          String(opt.trl),
        ];
      }),
    ];
    rows.push(cols.join(","));
  }

  // Totals row
  rows.push("");
  rows.push([
    "TOTAL CAPEX (EUR)",
    ...allStrategies.flatMap((s) => {
      const total = strategies[s].totalCapexEur;
      return ["", "", "", formatEur(total), String(total), "", "", ""];
    }),
  ].join(","));

  const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
  downloadBlob(blob, `procurement-comparison-${plantName.replace(/\s+/g, "-").toLowerCase()}.csv`);
}

/* ═══════════════════════════ PDF EXPORT (HTML-to-print) ═══════════════════════════ */

export function downloadPDF(nodes: Node[], plantName: string) {
  const { strategies, equipmentEntries } = buildComparisonReport(nodes, plantName);
  const allStrategies: ProcurementStrategy[] = ["bestPrice", "bestEfficiency", "economiesOfScale"];
  const strategyColors = { bestPrice: "#22c55e", bestEfficiency: "#3b82f6", economiesOfScale: "#f59e0b" };

  const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Procurement Report, ${escapeHtml(plantName)}</title>
  <style>
    @page { margin: 1cm; size: landscape; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 10px; color: #1a1a2e; margin: 0; padding: 20px; }
    h1 { font-size: 16px; margin: 0 0 4px 0; }
    h2 { font-size: 12px; margin: 16px 0 8px 0; color: #555; }
    .meta { color: #888; font-size: 9px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
    th, td { border: 1px solid #ddd; padding: 5px 8px; text-align: left; }
    th { background: #f5f5f5; font-weight: 600; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; }
    td { font-size: 10px; }
    .strategy-header { color: white; font-weight: 700; text-align: center; }
    .price { font-family: 'SF Mono', 'Consolas', monospace; font-weight: 700; }
    .total-row { background: #f0f9ff; font-weight: 700; }
    .total-row td { border-top: 2px solid #333; }
    .badge { display: inline-block; padding: 1px 6px; border-radius: 8px; font-size: 8px; font-weight: 600; }
    .lowest { background: #dcfce7; color: #166534; }
    .summary { display: flex; gap: 20px; margin-top: 16px; }
    .summary-card { flex: 1; border: 1px solid #ddd; border-radius: 8px; padding: 12px; text-align: center; }
    .summary-card h3 { font-size: 9px; text-transform: uppercase; color: #888; margin: 0 0 4px 0; }
    .summary-card .value { font-size: 18px; font-family: 'SF Mono', monospace; font-weight: 700; }
  </style>
</head>
<body>
  <h1>Procurement Comparison Report</h1>
  <p class="meta">${escapeHtml(plantName)}, Generated ${new Date().toLocaleDateString()} at ${new Date().toLocaleTimeString()}</p>

  <div class="summary">
    ${allStrategies.map((s) => `
      <div class="summary-card" style="border-color: ${strategyColors[s]}40">
        <h3 style="color: ${strategyColors[s]}">${strategyLabels[s].label}</h3>
        <div class="value" style="color: ${strategyColors[s]}">${formatEur(strategies[s].totalCapexEur)}</div>
        <p style="font-size: 8px; color: #888; margin: 2px 0 0 0">${strategyLabels[s].description}</p>
      </div>
    `).join("")}
  </div>

  <h2>Equipment Comparison</h2>
  <table>
    <thead>
      <tr>
        <th rowspan="2" style="vertical-align: bottom; width: 14%">Equipment</th>
        ${allStrategies.map((s) => `
          <th colspan="4" class="strategy-header" style="background: ${strategyColors[s]}">${strategyLabels[s].label}</th>
        `).join("")}
      </tr>
      <tr>
        ${allStrategies.map(() => `
          <th>Manufacturer / Model</th>
          <th>Price</th>
          <th>Efficiency</th>
          <th>Lead / TRL</th>
        `).join("")}
      </tr>
    </thead>
    <tbody>
      ${equipmentEntries.map(({ label, entry }) => {
        const prices = allStrategies.map((s) => entry[s].priceEur);
        const minPrice = Math.min(...prices);
        return `
          <tr>
            <td style="font-weight: 600">${label}</td>
            ${allStrategies.map((s, i) => {
              const opt = entry[s];
              const isLowest = prices[i] === minPrice;
              return `
                <td>
                  <div style="font-weight: 600">${opt.manufacturer}</div>
                  <div style="color: #888; font-size: 9px">${opt.model}</div>
                  <div style="color: #888; font-size: 8px">${opt.country}</div>
                </td>
                <td class="price" style="color: ${strategyColors[s]}">
                  ${opt.priceDisplay}
                  ${isLowest ? '<br><span class="badge lowest">LOWEST</span>' : ''}
                </td>
                <td style="font-size: 9px">${opt.efficiency}</td>
                <td style="font-size: 9px">${opt.leadTimeMonths} mo · TRL ${opt.trl}</td>
              `;
            }).join("")}
          </tr>
        `;
      }).join("")}
      <tr class="total-row">
        <td>TOTAL CAPEX</td>
        ${allStrategies.map((s) => `
          <td></td>
          <td class="price" style="color: ${strategyColors[s]}; font-size: 12px">${formatEur(strategies[s].totalCapexEur)}</td>
          <td></td>
          <td></td>
        `).join("")}
      </tr>
    </tbody>
  </table>

  <p style="color: #aaa; font-size: 8px; margin-top: 20px; text-align: center">
    Generated by GreenEarthX Plant Builder · Prices are indicative market estimates (2024-2025) and subject to negotiation
  </p>
</body>
</html>`;

  const printWindow = window.open("", "_blank");
  if (printWindow) {
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.onload = () => {
      printWindow.print();
    };
  }
}

/* ═══════════════════════════ Helpers ═══════════════════════════ */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatEur(v: number): string {
  if (v >= 1_000_000) return `€${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `€${(v / 1_000).toFixed(0)}k`;
  return `€${v}`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ═══════════════════════════ Persist to localStorage for dashboard ═══════════════════════════ */

export interface PersistedProcurement {
  plantId: string;
  plantName: string;
  strategy: ProcurementStrategy;
  timestamp: string;
  lineItems: ProcurementLineItem[];
  totalCapexEur: number;
}

export function persistProcurementToPlant(
  plantId: string,
  plantName: string,
  nodes: Node[],
  strategy: ProcurementStrategy
) {
  const report = buildProcurementReport(nodes, strategy, plantName);
  const data: PersistedProcurement = {
    plantId,
    plantName,
    strategy,
    timestamp: new Date().toISOString(),
    lineItems: report.lineItems,
    totalCapexEur: report.totalCapexEur,
  };
  localStorage.setItem(`procurement:${plantId}`, JSON.stringify(data));
  return data;
}

export function getPersistedProcurement(plantId: string): PersistedProcurement | null {
  const raw = localStorage.getItem(`procurement:${plantId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
