import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { getWorkspaceIds, getWorkspace } from '@/config/workspaces'

export function WorkspaceSwitcher() {
  const { currentWorkspace, setWorkspace } = useWorkspace()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const workspaceIds = getWorkspaceIds()

  const colorClasses: Record<string, { bg: string; text: string; border: string }> = {
    emerald: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
    blue: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
    purple: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' },
    red: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
    gray: { bg: 'bg-gray-50', text: 'text-gray-700', border: 'border-gray-200' },
  }

  const currentColors = colorClasses[currentWorkspace.color] || colorClasses.emerald

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${currentColors.bg} ${currentColors.text} ${currentColors.border} hover:opacity-80 transition-opacity`}
      >
        <span className="text-xs font-medium text-gray-500">Workspace:</span>
        <span className="font-bold">{currentWorkspace.name}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl border border-gray-200 shadow-lg z-50 overflow-hidden">
          <div className="p-3 border-b border-gray-100 bg-gray-50">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Switch Workspace
            </div>
          </div>

          <div className="py-2">
            {workspaceIds.map((id) => {
              const workspace = getWorkspace(id)
              const colors = colorClasses[workspace.color]
              const isActive = id === currentWorkspace.id

              return (
                <button
                  key={id}
                  onClick={() => {
                    setWorkspace(id)
                    setIsOpen(false)
                  }}
                  className={`w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-50 transition-colors ${
                    isActive ? 'bg-gray-50' : ''
                  }`}
                >
                  <div className={`w-10 h-10 rounded-lg ${colors.bg} flex items-center justify-center flex-shrink-0`}>
                    <div className={`text-lg font-black ${colors.text}`}>
                      {workspace.name.charAt(0)}
                    </div>
                  </div>

                  <div className="flex-1 text-left">
                    <div className="flex items-center gap-2">
                      <div className="font-bold text-gray-900">{workspace.name}</div>
                      {isActive && <Check className="w-4 h-4 text-emerald-600" />}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {workspace.description}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          <div className="p-3 border-t border-gray-100 bg-gray-50">
            <div className="text-xs text-gray-500">
              Your workspace determines which tools and data you see
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
