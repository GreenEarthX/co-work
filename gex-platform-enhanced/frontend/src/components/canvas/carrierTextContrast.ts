/**
 * Pure helper used by CarrierNode to derive a readable text/icon color for
 * a custom-tinted carrier bubble. Extracted so it can be unit-tested
 * independently of React.
 *
 * Strategy: blend the brand color with white at `alpha` to compute the
 * effective bubble background, then darken the brand color in 10% steps
 * until WCAG AA (>= 4.5:1) is reached against that background.
 */
import { contrastRatio } from "@/lib/carrierColorOverrides";

export interface Rgb { r: number; g: number; b: number }

export function blendOverWhite(rgb: Rgb, alpha: number): Rgb {
  return {
    r: Math.round(rgb.r * alpha + 255 * (1 - alpha)),
    g: Math.round(rgb.g * alpha + 255 * (1 - alpha)),
    b: Math.round(rgb.b * alpha + 255 * (1 - alpha)),
  };
}

export function deriveCarrierTextRgb(brand: Rgb, alpha: number, target = 4.5): Rgb {
  const bg = blendOverWhite(brand, alpha);
  let factor = 1;
  let text = { ...brand };
  while (factor > 0.1 && contrastRatio(text, bg) < target) {
    factor -= 0.1;
    text = {
      r: Math.round(brand.r * factor),
      g: Math.round(brand.g * factor),
      b: Math.round(brand.b * factor),
    };
  }
  return text;
}

/**
 * Pick pure black or white text for maximum legibility against a given
 * background color. Used for carrier bubbles when zoomed out — high-contrast
 * monochrome text reads far better than tinted variants of the brand color.
 */
export function pickReadableTextOnBackground(bg: Rgb): Rgb {
  const white = { r: 255, g: 255, b: 255 };
  const black = { r: 17, g: 24, b: 39 }; // slate-900-ish, slightly softer than #000
  return contrastRatio(white, bg) >= contrastRatio(black, bg) ? white : black;
}