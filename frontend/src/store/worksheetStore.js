import { create } from 'zustand';
import { temporal } from 'zundo';
import { ZOOM_LIMITS, HISTORY_LIMIT } from '../utils/constants';
import { clamp, generateId } from '../utils/helpers';
import { unwrapFromTemplate } from '../engine/templateWrapper';
import { unwrapFromSinhalaTemplate } from '../engine/sinhalaTemplateWrapper';

const useWorksheetStore = create()(
  temporal(
    (set, get) => ({
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
  )
);

export default useWorksheetStore;
