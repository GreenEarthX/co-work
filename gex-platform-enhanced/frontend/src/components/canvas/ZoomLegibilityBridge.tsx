/**
 * ZoomLegibilityBridge — keeps node labels readable when the canvas is
 * zoomed out (presentations, large plants). Reads the live React Flow
 * zoom and writes a CSS variable `--zoom-boost` on the nearest
 * `.react-flow` wrapper. Node label classes (.canvas-node-label,
 * .canvas-node-id) consume that variable to grow their font-size
 * inversely to the zoom — they never shrink below their natural size
 * (boost is clamped to >= 1) and they cap at ~2.4x so they don't
 * overflow the node bubble.
 *
 * Mount inside <ReactFlow> so `useStore` resolves the active instance.
 */
// Zoom-based label scaling has been disabled by user request.
// Labels render at their natural CSS size at every zoom level.
export default function ZoomLegibilityBridge() {
  return null;
}
