/**
 * ISO 10628 / IEC 62424 inspired P&ID symbol components.
 * Each icon accepts the same props as lucide-react icons (size, color, className, etc.)
 * so they can be used interchangeably in the icon registry.
 */
import React from "react";

interface PidIconProps extends React.SVGAttributes<SVGSVGElement> {
  size?: number | string;
  color?: string;
  strokeWidth?: number | string;
}

const defaults = (props: PidIconProps) => ({
  width: props.size ?? 24,
  height: props.size ?? 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: props.color ?? "currentColor",
  strokeWidth: props.strokeWidth ?? 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  xmlns: "http://www.w3.org/2000/svg",
});

/* ══════════════════════════════════════════════
   PUMPS, ISO circle + triangle
   ══════════════════════════════════════════════ */
export const PidPump = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    <polygon points="8,16 12,6 16,16" fill="none" stroke={props.color ?? "currentColor"} />
  </svg>
);
PidPump.displayName = "PidPump";

/* ══════════════════════════════════════════════
   COMPRESSOR, ISO circle + angular intake/exhaust
   ══════════════════════════════════════════════ */
export const PidCompressor = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    {/* Blade/vane lines */}
    <line x1="7" y1="16" x2="12" y2="6" />
    <line x1="17" y1="16" x2="12" y2="6" />
    <line x1="7" y1="16" x2="17" y2="16" />
  </svg>
);
PidCompressor.displayName = "PidCompressor";

/* ══════════════════════════════════════════════
   HEAT EXCHANGER, ISO circle with S-curve
   ══════════════════════════════════════════════ */
export const PidHeatExchanger = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M8 8 C10 8, 10 12, 12 12 S14 16, 16 16" />
    <path d="M8 16 C10 16, 10 12, 12 12 S14 8, 16 8" />
  </svg>
);
PidHeatExchanger.displayName = "PidHeatExchanger";

/* ══════════════════════════════════════════════
   VALVE, ISO bowtie (two triangles)
   ══════════════════════════════════════════════ */
export const PidValve = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <polygon points="4,6 12,12 4,18" fill="none" stroke={props.color ?? "currentColor"} />
    <polygon points="20,6 12,12 20,18" fill="none" stroke={props.color ?? "currentColor"} />
  </svg>
);
PidValve.displayName = "PidValve";

/* ══════════════════════════════════════════════
   VESSEL / REACTOR, ISO rounded-top rectangle
   ══════════════════════════════════════════════ */
export const PidReactor = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <path d="M6 8 C6 4, 18 4, 18 8 L18 20 H6 Z" />
    {/* Internal agitator line */}
    <line x1="12" y1="8" x2="12" y2="17" />
    <line x1="9" y1="14" x2="15" y2="14" />
  </svg>
);
PidReactor.displayName = "PidReactor";

/* ══════════════════════════════════════════════
   TANK / STORAGE, ISO cylinder (flat bottom)
   ══════════════════════════════════════════════ */
export const PidTank = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <ellipse cx="12" cy="6" rx="7.5" ry="3" />
    <path d="M4.5 6 V18" />
    <path d="M19.5 6 V18" />
    <ellipse cx="12" cy="18" rx="7.5" ry="3" />
  </svg>
);
PidTank.displayName = "PidTank";

/* ══════════════════════════════════════════════
   COLUMN, ISO tall vessel with trays
   ══════════════════════════════════════════════ */
export const PidColumn = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <path d="M8 4 C8 2, 16 2, 16 4 L16 20 C16 22, 8 22, 8 20 Z" />
    {/* Internal tray lines */}
    <line x1="8.5" y1="8" x2="15.5" y2="8" strokeDasharray="1.5 1" />
    <line x1="8.5" y1="12" x2="15.5" y2="12" strokeDasharray="1.5 1" />
    <line x1="8.5" y1="16" x2="15.5" y2="16" strokeDasharray="1.5 1" />
  </svg>
);
PidColumn.displayName = "PidColumn";

/* ══════════════════════════════════════════════
   ELECTROLYZER, ISO cell with electrodes
   ══════════════════════════════════════════════ */
export const PidElectrolyzer = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    {/* Anode + Cathode */}
    <line x1="9" y1="7" x2="9" y2="17" />
    <line x1="15" y1="7" x2="15" y2="17" />
    {/* + and - */}
    <line x1="6" y1="10" x2="8" y2="10" />
    <line x1="7" y1="9" x2="7" y2="11" />
    <line x1="16" y1="10" x2="18" y2="10" />
    {/* Bubble lines */}
    <circle cx="11" cy="12" r="0.6" fill={props.color ?? "currentColor"} stroke="none" />
    <circle cx="13" cy="10" r="0.6" fill={props.color ?? "currentColor"} stroke="none" />
    <circle cx="12" cy="14" r="0.6" fill={props.color ?? "currentColor"} stroke="none" />
  </svg>
);
PidElectrolyzer.displayName = "PidElectrolyzer";

/* ══════════════════════════════════════════════
   FILTER / PURIFIER, ISO diamond with dots
   ══════════════════════════════════════════════ */
export const PidFilter = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    {/* Filter medium, horizontal dashed lines */}
    <line x1="4" y1="10" x2="20" y2="10" strokeDasharray="2 1.5" />
    <line x1="4" y1="14" x2="20" y2="14" strokeDasharray="2 1.5" />
  </svg>
);
PidFilter.displayName = "PidFilter";

/* ══════════════════════════════════════════════
   TURBINE, ISO circle with blades
   ══════════════════════════════════════════════ */
export const PidTurbine = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    {/* Blade arcs */}
    <path d="M12 4 C16 8, 16 16, 12 20" />
    <path d="M12 4 C8 8, 8 16, 12 20" />
  </svg>
);
PidTurbine.displayName = "PidTurbine";

/* ══════════════════════════════════════════════
   BOILER / FIRED HEATER, ISO rectangle with flame
   ══════════════════════════════════════════════ */
export const PidBoiler = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    {/* Flame symbol */}
    <path d="M10 18 C10 14, 12 13, 12 10 C12 13, 14 14, 14 18" />
    <path d="M11 18 C11 16, 12 15, 12 13 C12 15, 13 16, 13 18" />
  </svg>
);
PidBoiler.displayName = "PidBoiler";

/* ══════════════════════════════════════════════
   WATER TREATMENT, ISO vessel with wave
   ══════════════════════════════════════════════ */
export const PidWaterTreatment = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    {/* Water wave */}
    <path d="M5 13 C7 11, 9 15, 11 13 C13 11, 15 15, 19 13" />
    {/* Drop */}
    <path d="M12 6 L14 10 C14 11.5, 10 11.5, 10 10 Z" />
  </svg>
);
PidWaterTreatment.displayName = "PidWaterTreatment";

/* ══════════════════════════════════════════════
   MIXER, ISO circle with X
   ══════════════════════════════════════════════ */
export const PidMixer = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    <line x1="6" y1="6" x2="18" y2="18" />
    <line x1="18" y1="6" x2="6" y2="18" />
  </svg>
);
PidMixer.displayName = "PidMixer";

/* ══════════════════════════════════════════════
   SEPARATOR, ISO vessel with horizontal divider
   ══════════════════════════════════════════════ */
export const PidSeparator = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <path d="M6 4 C6 2, 18 2, 18 4 L18 20 C18 22, 6 22, 6 20 Z" />
    <line x1="6" y1="12" x2="18" y2="12" />
    <line x1="6" y1="15" x2="18" y2="15" strokeDasharray="2 1" />
  </svg>
);
PidSeparator.displayName = "PidSeparator";

/* ══════════════════════════════════════════════
   FUEL CELL / POWER, ISO rectangle with lightning
   ══════════════════════════════════════════════ */
export const PidFuelCell = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    {/* Lightning bolt */}
    <polyline points="13,6 10,12 14,12 11,18" />
  </svg>
);
PidFuelCell.displayName = "PidFuelCell";

/* ══════════════════════════════════════════════
   DAC / CARBON CAPTURE, ISO column with arrows
   ══════════════════════════════════════════════ */
export const PidDac = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="5" y="3" width="14" height="18" rx="1.5" />
    {/* Air flow arrows */}
    <path d="M2 8 L5 8" />
    <path d="M2 12 L5 12" />
    <path d="M2 16 L5 16" />
    {/* Packed bed dots */}
    <circle cx="10" cy="9" r="0.7" fill={props.color ?? "currentColor"} stroke="none" />
    <circle cx="14" cy="9" r="0.7" fill={props.color ?? "currentColor"} stroke="none" />
    <circle cx="12" cy="12" r="0.7" fill={props.color ?? "currentColor"} stroke="none" />
    <circle cx="10" cy="15" r="0.7" fill={props.color ?? "currentColor"} stroke="none" />
    <circle cx="14" cy="15" r="0.7" fill={props.color ?? "currentColor"} stroke="none" />
  </svg>
);
PidDac.displayName = "PidDac";

/* ══════════════════════════════════════════════
   COOLER, ISO circle with fan blades
   ══════════════════════════════════════════════ */
export const PidCooler = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    {/* Fan blades */}
    <path d="M12 4 C14 8, 14 8, 12 12" />
    <path d="M12 12 C16 14, 16 14, 20 12" />
    <path d="M12 12 C10 16, 10 16, 12 20" />
    <path d="M12 12 C8 10, 8 10, 4 12" />
    <circle cx="12" cy="12" r="1.5" />
  </svg>
);
PidCooler.displayName = "PidCooler";

/* ══════════════════════════════════════════════
   BLOWER / FAN, ISO circle with blade
   ══════════════════════════════════════════════ */
export const PidBlower = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 5 L15 12 L12 19" />
    <path d="M12 5 L9 12 L12 19" />
  </svg>
);
PidBlower.displayName = "PidBlower";

/* ══════════════════════════════════════════════
   REFORMER, ISO rectangle with serpentine
   ══════════════════════════════════════════════ */
export const PidReformer = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    {/* Serpentine / coil */}
    <path d="M7 7 L17 7 L17 10 L7 10 L7 13 L17 13 L17 17" strokeLinejoin="round" />
  </svg>
);
PidReformer.displayName = "PidReformer";

/* ══════════════════════════════════════════════
   DRYER, ISO rectangle with wave + arrow up
   ══════════════════════════════════════════════ */
export const PidDryer = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="16" height="16" rx="1.5" />
    <path d="M8 14 C9 12, 11 16, 12 14 C13 12, 15 16, 16 14" />
    <line x1="12" y1="6" x2="12" y2="11" />
    <polyline points="10,8 12,6 14,8" />
  </svg>
);
PidDryer.displayName = "PidDryer";

/* ══════════════════════════════════════════════
   GASIFIER, ISO reactor with upward flow
   ══════════════════════════════════════════════ */
export const PidGasifier = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <path d="M6 8 C6 4, 18 4, 18 8 L18 20 H6 Z" />
    {/* Upward flow arrows */}
    <line x1="10" y1="17" x2="10" y2="10" />
    <polyline points="8.5,12 10,10 11.5,12" />
    <line x1="14" y1="17" x2="14" y2="10" />
    <polyline points="12.5,12 14,10 15.5,12" />
  </svg>
);
PidGasifier.displayName = "PidGasifier";

/* ══════════════════════════════════════════════
   GATE INPUT, ISO arrow into boundary
   ══════════════════════════════════════════════ */
export const PidGateInput = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="12" y="4" width="8" height="16" rx="1" />
    <line x1="3" y1="12" x2="12" y2="12" />
    <polyline points="9,9 12,12 9,15" />
  </svg>
);
PidGateInput.displayName = "PidGateInput";

/* ══════════════════════════════════════════════
   GATE OUTPUT, ISO arrow out of boundary
   ══════════════════════════════════════════════ */
export const PidGateOutput = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="4" y="4" width="8" height="16" rx="1" />
    <line x1="12" y1="12" x2="21" y2="12" />
    <polyline points="18,9 21,12 18,15" />
  </svg>
);
PidGateOutput.displayName = "PidGateOutput";

/* ══════════════════════════════════════════════
   CONVEYOR, ISO horizontal with rollers
   ══════════════════════════════════════════════ */
export const PidConveyor = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <line x1="3" y1="14" x2="21" y2="14" />
    <circle cx="6" cy="17" r="2.5" />
    <circle cx="18" cy="17" r="2.5" />
    <line x1="8.5" y1="17" x2="15.5" y2="17" />
    {/* Belt top */}
    <line x1="6" y1="14.5" x2="18" y2="14.5" />
  </svg>
);
PidConveyor.displayName = "PidConveyor";

/* ══════════════════════════════════════════════
   FLARE, ISO flame stack
   ══════════════════════════════════════════════ */
export const PidFlare = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <line x1="12" y1="22" x2="12" y2="10" />
    <path d="M9 10 L12 3 L15 10" />
    {/* Flame tip */}
    <path d="M10 6 C11 4, 13 4, 14 6" />
  </svg>
);
PidFlare.displayName = "PidFlare";

/* ══════════════════════════════════════════════
   LOADING UNIT, ISO truck with arrow
   ══════════════════════════════════════════════ */
export const PidLoading = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <rect x="3" y="8" width="14" height="10" rx="1" />
    <polyline points="17,12 17,8 21,12 17,16 17,12" />
    <circle cx="7" cy="20" r="1.5" />
    <circle cx="13" cy="20" r="1.5" />
  </svg>
);
PidLoading.displayName = "PidLoading";

/* ══════════════════════════════════════════════
   GENERIC CARRIER, ISO circle with dot
   ══════════════════════════════════════════════ */
export const PidCarrier = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="2" fill={props.color ?? "currentColor"} stroke="none" />
  </svg>
);
PidCarrier.displayName = "PidCarrier";

/* ══════════════════════════════════════════════
   PIPELINE, ISO double line with flow arrow
   ══════════════════════════════════════════════ */
export const PidPipeline = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <line x1="3" y1="10" x2="21" y2="10" />
    <line x1="3" y1="14" x2="21" y2="14" />
    <polyline points="16,8 20,12 16,16" />
  </svg>
);
PidPipeline.displayName = "PidPipeline";

/* ══════════════════════════════════════════════
   METERING, ISO circle with M
   ══════════════════════════════════════════════ */
export const PidMeter = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <circle cx="12" cy="12" r="8.5" />
    <text x="12" y="15.5" textAnchor="middle" fontSize="9" fontWeight="700"
      fill={props.color ?? "currentColor"} stroke="none" fontFamily="sans-serif">M</text>
  </svg>
);
PidMeter.displayName = "PidMeter";

/* ══════════════════════════════════════════════
   SAFETY / RELIEF, ISO spring valve symbol
   ══════════════════════════════════════════════ */
export const PidSafety = (props: PidIconProps) => (
  <svg {...defaults(props)} className={props.className}>
    <polygon points="4,18 12,6 20,18" fill="none" stroke={props.color ?? "currentColor"} />
    <line x1="12" y1="10" x2="12" y2="14" />
    <circle cx="12" cy="16" r="0.8" fill={props.color ?? "currentColor"} stroke="none" />
  </svg>
);
PidSafety.displayName = "PidSafety";
