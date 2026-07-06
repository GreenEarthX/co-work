// Screen: Shared component — CISO-gated screens
import React, { useState, useEffect } from 'react';
import { X, ShieldCheck } from 'lucide-react';

export function CISOGate({
  isOpen,
  onClose,
  onAuthenticated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onAuthenticated: () => void;
}) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [shake, setShake] = useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const CISO_PASSWORD = localStorage.getItem('gex_ciso_password') || 'Enter-123';

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (password === CISO_PASSWORD) {
      setError(false);
      setPassword('');
      sessionStorage.setItem('gex_ciso_session', 'true');
      onAuthenticated();
    } else {
      setError(true);
      setShake(true);
      setTimeout(() => setShake(false), 500);
      setPassword('');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className={`bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-6 w-96 ${
          shake ? 'animate-shake' : ''
        }`}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            <span className="text-sm font-bold text-indigo-300 uppercase tracking-wider">
              CISO Administration
            </span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-xs text-gray-400 mb-4">
          Enter the company security password to access administration tools.
        </p>
        <form onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(false); }}
            placeholder="CISO password"
            className={`w-full px-3 py-2 rounded-lg text-sm font-mono
              bg-gray-800 border ${error ? 'border-red-500' : 'border-gray-600'}
              text-gray-200 placeholder-gray-500
              focus:outline-none focus:ring-2 focus:ring-indigo-500`}
            autoComplete="off"
          />
          {error && (
            <p className="text-xs text-red-400 mt-1">Incorrect password</p>
          )}
          <button
            type="submit"
            className="w-full mt-3 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500
              text-white text-sm font-medium transition-colors"
          >
            Authenticate
          </button>
        </form>
      </div>
    </div>
  );
}
