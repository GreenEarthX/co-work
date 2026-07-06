/**
 * useLocalPersistence — Helpers for reading/writing JSON to localStorage.
 */

const PREFIX = "ptool_";

export function loadFromStorage<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function saveToStorage<T>(key: string, data: T): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(data));
  } catch {
    // quota exceeded — silently fail
  }
}

export function clearStorage(key: string): void {
  localStorage.removeItem(PREFIX + key);
}
