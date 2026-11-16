/**
 * Links into the market, and whether the signed-in role may follow them.
 *
 * Discovery review (13 Nov 2026, F17): "Scan Supplier Offers", "Match Offers", "Review Market
 * Bids" and "Scan Buyer RFQs" all opened Your Matches — the company's own proposals — instead
 * of the market. A button names where it lands and lands in the state it promises, so each one
 * now opens Market Discovery on the side it names (supply or demand), filtered to the molecule
 * in hand. And a button never leads to a screen the role is refused: `useCanOpen` asks the same
 * rule as the menu and the route guard (menuArchitecture.isVisible).
 */
import { useUserRole } from '@/contexts/UserRoleContext'
import { isVisible } from '@/config/menuArchitecture'
import { menuItemsForPath } from '@/components/MenuAccessGuard'

export type MarketSide = 'supply' | 'demand'

export const MARKET_DISCOVERY = '/market-discovery'

export function marketDiscoveryPath(side: MarketSide, molecule?: string | null): string {
  const q = new URLSearchParams({ side })
  if (molecule && molecule !== 'all') q.set('molecule', molecule)
  return `${MARKET_DISCOVERY}?${q.toString()}`
}

/** May the signed-in role open this path? A path with no menu entry is not gated by the menu. */
export function useCanOpen(path: string): boolean {
  const { role } = useUserRole()
  const items = menuItemsForPath(path.split('?')[0])
  return items.length === 0 || items.some(i => isVisible(i, role))
}
