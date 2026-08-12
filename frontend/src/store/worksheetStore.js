import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { temporal } from 'zundo';
import { ZOOM_LIMITS, HISTORY_LIMIT } from '../utils/constants';
import { clamp, generateId } from '../utils/helpers';
import { unwrapFromTemplate } from '../engine/templateWrapper';
import { unwrapFromSinhalaTemplate } from '../engine/sinhalaTemplateWrapper';
import { nanoid } from 'nanoid';

// ═══════════════════════════════════════════════════════════════════
// MULTI-TAB ISOLATION
// ═══════════════════════════════════════════════════════════════════
//
// Problem: localStorage is shared across ALL tabs of the same origin.
//          Opening a second tab overwrites the first tab's worksheet.
//
// Solution: Each tab uses its own sessionStorage (tab-scoped by spec)
//           as the primary store. A lightweight registry in localStorage
//           enables crash-recovery from the Dashboard.
//
// Architecture:
//   sessionStorage["gb-ws-tabId"]   → unique tab identifier
//   sessionStorage["gb-ws-active"]  → full worksheet state (live)
//   localStorage["gb-session-registry"] → [{tabId, title, lang, ts}, ...]
//   localStorage["gb-session-<tabId>"]  → backup of worksheet state
// ═══════════════════════════════════════════════════════════════════

const SESSION_REGISTRY_KEY = 'gb-session-registry';
const SESSION_BACKUP_PREFIX = 'gb-session-';
const TAB_ID_KEY = 'gb-ws-tabId';
const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000; // 24 hours

// ── Tab ID: reuse on refresh, generate on fresh tab ──
function getOrCreateTabId() {
  let tabId = sessionStorage.getItem(TAB_ID_KEY);
  if (!tabId) {
    tabId = nanoid(10);
    sessionStorage.setItem(TAB_ID_KEY, tabId);
  }
  return tabId;
}

// ── Custom storage adapter: sessionStorage (tab-isolated) ──
const sessionStorageAdapter = {
  getItem: (name) => {
    const value = sessionStorage.getItem(name);
    return value ?? null;
  },
  setItem: (name, value) => {
    sessionStorage.setItem(name, value);
  },
  removeItem: (name) => {
    sessionStorage.removeItem(name);
  },
};

// ── Session Registry Helpers (localStorage, cross-tab) ──

/** Read the session registry array from localStorage */
export function readSessionRegistry() {
  try {
    const raw = localStorage.getItem(SESSION_REGISTRY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Write the session registry array to localStorage */
function writeSessionRegistry(entries) {
  try {
    localStorage.setItem(SESSION_REGISTRY_KEY, JSON.stringify(entries));
  } catch { /* storage full — ignore */ }
}

/** Update or insert this tab's entry in the registry */
function upsertRegistryEntry(tabId, meta) {
  const entries = readSessionRegistry();
  const idx = entries.findIndex((e) => e.tabId === tabId);
  const entry = {
    tabId,
    title: meta.title || 'Untitled Worksheet',
    lang: meta.lang || 'en',
    timestamp: Date.now(),
  };
  if (idx >= 0) entries[idx] = entry;
  else entries.push(entry);
  writeSessionRegistry(entries);
}

/** Remove a tab's entry from the registry + its backup */
export function removeRegistryEntry(tabId) {
  const entries = readSessionRegistry().filter((e) => e.tabId !== tabId);
  writeSessionRegistry(entries);
  try { localStorage.removeItem(SESSION_BACKUP_PREFIX + tabId); } catch {}
}

/** Garbage-collect stale entries (>24h old) */
export function gcStaleEntries() {
  const now = Date.now();
  const entries = readSessionRegistry();
  const stale = entries.filter((e) => now - e.timestamp > STALE_THRESHOLD_MS);
  stale.forEach((e) => {
    try { localStorage.removeItem(SESSION_BACKUP_PREFIX + e.tabId); } catch {}
  });
  writeSessionRegistry(entries.filter((e) => now - e.timestamp <= STALE_THRESHOLD_MS));
}

/** Write a full backup of the worksheet state to localStorage for crash recovery */
function writeBackup(tabId, state) {
  try {
    const backup = {
      worksheetLang: state.worksheetLang,
      rawHTML: state.rawHTML,
      originalHTML: state.originalHTML,
      draftHTML: state.draftHTML,
      hasUnsavedChanges: state.hasUnsavedChanges,
      worksheetMeta: state.worksheetMeta,
      blocks: state.blocks,
      _reloadCounter: state._reloadCounter,
    };
    localStorage.setItem(SESSION_BACKUP_PREFIX + tabId, JSON.stringify(backup));
  } catch { /* storage full — ignore */ }
}

/** Read a backup from localStorage */
export function readBackup(tabId) {
  try {
    const raw = localStorage.getItem(SESSION_BACKUP_PREFIX + tabId);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// ── Debounced registry+backup writer ──
let _registryTimer = null;
function debouncedRegistryUpdate(tabId, state) {
  if (_registryTimer) clearTimeout(_registryTimer);
  _registryTimer = setTimeout(() => {
    if (state.draftHTML || state.originalHTML) {
      upsertRegistryEntry(tabId, {
        title: state.worksheetMeta?.title,
        lang: state.worksheetLang,
      });
      writeBackup(tabId, state);
    }
    _registryTimer = null;
  }, 2000); // 2s debounce — avoids thrashing localStorage on every keystroke
}

// ═══════════════════════════════════════════════════════════════════

const TAB_ID = getOrCreateTabId();

const useWorksheetStore = create()(
  persist(
    temporal(
      (set, get) => ({
      // === Tab Identity ===
      _tabId: TAB_ID,

      // === View State ===
      view: 'auth', // 'auth' | 'dashboard' | 'upload' | 'upload-sinhala' | 'editor'

      // === Language ===
      worksheetLang: 'en', // 'en' | 'si'

      // === Worksheet Data ===
      rawHTML: '',            // The raw HTML string pasted by the user
      originalHTML: '',       // Last saved version
      draftHTML: '',           // Current unsaved edits
      hasUnsavedChanges: false,
      worksheetMeta: {
        title: 'Untitled Worksheet',
        width: 1100,
        height: 800,
      },

      // === Block Data (structural regions) ===
      blocks: [],

      // === Element Selection ===
      selectedElement: null,

      // === Editor UI State ===
      selectedBlockIds: [],
      zoom: 1,
      panOffset: { x: 0, y: 0 },
      showGrid: true,
      showExportModal: false,
      readOnly: false,

      // === Actions: View ===
      setView: (view) => set({ view }),
      setReadOnly: (readOnly) => set({ readOnly }),
      setWorksheetLang: (lang) => set({ worksheetLang: lang }),

      // === Actions: Worksheet ===
      setRawHTML: (html) => set({ rawHTML: html }),
      setOriginalHTML: (html) => set({ originalHTML: html, draftHTML: html }),
      setWorksheetMeta: (meta) => set((s) => ({ worksheetMeta: { ...s.worksheetMeta, ...meta } })),

      // === Actions: Draft (unsaved edits) ===
      setDraftHTML: (html) => set((s) => ({
        draftHTML: html,
        hasUnsavedChanges: true,
        // Sync rawHTML so 'Edit Source' shows current state with all editor modifications
        rawHTML: s.worksheetLang === 'si' ? unwrapFromSinhalaTemplate(html) : unwrapFromTemplate(html),
      })),

      // Called after undo/redo restores a previous draftHTML — reload iframe
      _syncAfterUndoRedo: () => set((s) => {
        const unwrap = s.worksheetLang === 'si' ? unwrapFromSinhalaTemplate : unwrapFromTemplate;
        return {
          hasUnsavedChanges: s.draftHTML !== s.originalHTML,
          rawHTML: unwrap(s.draftHTML || s.originalHTML),
          _reloadCounter: (s._reloadCounter || 0) + 1,
        };
      }),

      saveChanges: () => set((s) => ({
        originalHTML: s.draftHTML || s.originalHTML,
        hasUnsavedChanges: false,
      })),

      discardChanges: () => set((s) => {
        const unwrap = s.worksheetLang === 'si' ? unwrapFromSinhalaTemplate : unwrapFromTemplate;
        return {
          draftHTML: s.originalHTML,
          hasUnsavedChanges: false,
          rawHTML: unwrap(s.originalHTML),
          _reloadCounter: (s._reloadCounter || 0) + 1,
        };
      }),

      _reloadCounter: 0,

      // === Actions: Element Selection ===
      setSelectedElement: (el) => set({ selectedElement: el }),

      // === Actions: Blocks ===
      setBlocks: (blocks) => set({ blocks }),
      addBlock: (block) => set((s) => ({ blocks: [...s.blocks, block] })),

      updateBlockPosition: (id, x, y) =>
        set((s) => ({ blocks: s.blocks.map((b) => b.id === id ? { ...b, position: { x, y } } : b) })),

      updateBlockSize: (id, width, height) =>
        set((s) => ({ blocks: s.blocks.map((b) => b.id === id ? { ...b, size: { width, height } } : b) })),

      updateBlockContent: (id, content) =>
        set((s) => ({
          blocks: s.blocks.map((b) =>
            b.id === id ? { ...b, content: { ...b.content, ...content } } : b
          ),
        })),

      updateBlockStyles: (id, styles) =>
        set((s) => ({
          blocks: s.blocks.map((b) =>
            b.id === id ? { ...b, styles: { ...b.styles, ...styles } } : b
          ),
        })),

      deleteBlocks: (ids) =>
        set((s) => ({
          blocks: s.blocks.filter((b) => !ids.includes(b.id)),
          selectedBlockIds: s.selectedBlockIds.filter((id) => !ids.includes(id)),
        })),

      duplicateBlocks: (ids) =>
        set((s) => {
          const newBlocks = s.blocks
            .filter((b) => ids.includes(b.id))
            .map((b) => ({
              ...b, id: generateId(),
              position: { x: b.position.x + 20, y: b.position.y + 20 },
            }));
          return { blocks: [...s.blocks, ...newBlocks] };
        }),

      toggleBlockLock: (id) =>
        set((s) => ({
          blocks: s.blocks.map((b) =>
            b.id === id ? { ...b, meta: { ...b.meta, locked: !b.meta.locked } } : b
          ),
        })),

      // === Actions: Selection ===
      setSelectedBlockIds: (ids) => set({ selectedBlockIds: ids }),
      selectBlock: (id, add = false) =>
        set((s) => ({
          selectedBlockIds: add
            ? s.selectedBlockIds.includes(id)
              ? s.selectedBlockIds.filter((sid) => sid !== id)
              : [...s.selectedBlockIds, id]
            : [id],
        })),
      clearSelection: () => set({ selectedBlockIds: [], selectedElement: null }),
      selectAll: () => set((s) => ({ selectedBlockIds: s.blocks.map((b) => b.id) })),

      // === Actions: Zoom & Pan ===
      setZoom: (zoom) => set({ zoom: clamp(zoom, ZOOM_LIMITS.min, ZOOM_LIMITS.max) }),
      zoomIn: () => set((s) => ({ zoom: clamp(s.zoom + ZOOM_LIMITS.step, ZOOM_LIMITS.min, ZOOM_LIMITS.max) })),
      zoomOut: () => set((s) => ({ zoom: clamp(s.zoom - ZOOM_LIMITS.step, ZOOM_LIMITS.min, ZOOM_LIMITS.max) })),
      setPanOffset: (offset) => set({ panOffset: offset }),

      fitToScreen: (cw, ch) =>
        set((s) => {
          const { width, height } = s.worksheetMeta;
          const zoom = clamp(Math.min((cw - 80) / width, (ch - 80) / height), ZOOM_LIMITS.min, ZOOM_LIMITS.max);
          return { zoom, panOffset: { x: 0, y: 0 } };
        }),

      // === Actions: Modals ===
      showCodeViewer: false,
      setShowExportModal: (show) => set({ showExportModal: show }),
      setShowCodeViewer: (show) => set({ showCodeViewer: show }),
      setShowGrid: (show) => set({ showGrid: show }),

      // === Actions: Session Recovery ===
      clearSession: () => {
        // Clean up this tab's sessionStorage persistence
        sessionStorage.removeItem('gb-ws-active');
        // Clean up registry + backup in localStorage
        removeRegistryEntry(TAB_ID);
        set({
          view: 'dashboard',
          worksheetLang: 'en',
          rawHTML: '',
          originalHTML: '',
          draftHTML: '',
          hasUnsavedChanges: false,
          blocks: [],
          selectedElement: null,
          selectedBlockIds: [],
          zoom: 1,
          panOffset: { x: 0, y: 0 },
          showGrid: true,
          showExportModal: false,
          showCodeViewer: false,
          readOnly: false,
          _reloadCounter: 0,
          worksheetMeta: { title: 'Untitled Worksheet', width: 1100, height: 800 },
        });
      },

      // === Actions: Restore from backup (used by Dashboard for crash recovery) ===
      restoreFromBackup: (backupData) => {
        set({
          ...backupData,
          view: 'editor',
        });
      },
    }),
    {
      partialize: (state) => ({ draftHTML: state.draftHTML }),
      limit: HISTORY_LIMIT,
      // Throttle history: only record a snapshot after 1s of inactivity
      // This batches rapid edits (typing, dragging) into single undo steps
      handleSet: (handleSet) => {
        let timeoutId = null;
        return (state) => {
          if (timeoutId) clearTimeout(timeoutId);
          timeoutId = setTimeout(() => {
            handleSet(state);
            timeoutId = null;
          }, 1000);
        };
      },
    }
  ),
  {
    name: 'gb-ws-active',
    // Use sessionStorage (tab-scoped) instead of localStorage (shared)
    storage: sessionStorageAdapter,
    // Only persist the essential worksheet data — not transient UI state
    partialize: (state) => ({
      view: state.view,
      worksheetLang: state.worksheetLang,
      rawHTML: state.rawHTML,
      originalHTML: state.originalHTML,
      draftHTML: state.draftHTML,
      hasUnsavedChanges: state.hasUnsavedChanges,
      worksheetMeta: state.worksheetMeta,
      blocks: state.blocks,
      _reloadCounter: state._reloadCounter,
    }),
  }
  )
);

// ── Subscribe to state changes → update registry + backup (debounced) ──
useWorksheetStore.subscribe((state) => {
  // Only backup when there's actual worksheet data worth saving
  if (state.view === 'editor' && (state.draftHTML || state.originalHTML)) {
    debouncedRegistryUpdate(TAB_ID, state);
  }
});

export default useWorksheetStore;
