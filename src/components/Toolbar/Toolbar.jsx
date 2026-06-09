import { useCallback, useEffect } from 'react';
import {
  Upload, Download, Undo2, Redo2, Save, RotateCcw,
  ZoomIn, ZoomOut, Grid3x3, Maximize
} from 'lucide-react';
import useWorksheetStore from '../../store/worksheetStore';

export default function Toolbar() {
  const zoom = useWorksheetStore((s) => s.zoom);
  const worksheetMeta = useWorksheetStore((s) => s.worksheetMeta);
  const hasUnsavedChanges = useWorksheetStore((s) => s.hasUnsavedChanges);
  const setZoom = useWorksheetStore((s) => s.setZoom);
  const zoomIn = useWorksheetStore((s) => s.zoomIn);
  const zoomOut = useWorksheetStore((s) => s.zoomOut);
  const showGrid = useWorksheetStore((s) => s.showGrid);
  const setShowGrid = useWorksheetStore((s) => s.setShowGrid);
  const setShowExportModal = useWorksheetStore((s) => s.setShowExportModal);
  const setView = useWorksheetStore((s) => s.setView);
  const saveChanges = useWorksheetStore((s) => s.saveChanges);
  const discardChanges = useWorksheetStore((s) => s.discardChanges);
  const fitToScreen = useWorksheetStore((s) => s.fitToScreen);

  const handleUndo = useCallback(() => {
    useWorksheetStore.temporal.getState().undo();
    setTimeout(() => useWorksheetStore.getState()._syncAfterUndoRedo(), 0);
  }, []);
  const handleRedo = useCallback(() => {
    useWorksheetStore.temporal.getState().redo();
    setTimeout(() => useWorksheetStore.getState()._syncAfterUndoRedo(), 0);
  }, []);

  useEffect(() => {
    const onKeyDown = (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); handleUndo(); }
      else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); handleRedo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); if (useWorksheetStore.getState().hasUnsavedChanges) saveChanges(); }
      else if ((e.ctrlKey || e.metaKey) && e.key === 'e') { e.preventDefault(); setShowExportModal(true); }
      else if (e.key === '0' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setZoom(1); }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleUndo, handleRedo, saveChanges, setShowExportModal, setZoom]);

  const handleNew = useCallback(() => {
    if (hasUnsavedChanges && !window.confirm('You have unsaved changes. Discard and start new?')) return;
    setView('upload');
  }, [hasUnsavedChanges, setView]);

  const handleFitToScreen = useCallback(() => {
    const container = document.querySelector('.flex-1.relative.overflow-hidden');
    if (container) fitToScreen(container.clientWidth, container.clientHeight);
  }, [fitToScreen]);

  const zoomPresets = [50, 75, 100, 125, 150, 200];

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-surface-200 shrink-0 shadow-sm" style={{ zIndex: 20 }}>
      {/* Left: Logo + Title + File actions */}
      <div className="flex items-center gap-2">
        <img src="/gb-logo.jpg" alt="GeniusBees" className="h-8 object-contain" />
        <div className="w-px h-6 bg-surface-200" />
        <span className="text-xs font-semibold text-surface-800 hidden sm:block truncate max-w-[160px]">
          {worksheetMeta.title || 'Worksheet'}
        </span>
        <div className="w-px h-6 bg-surface-200 hidden sm:block" />

        <button onClick={handleNew}
          className="text-xs flex items-center gap-1 px-2 py-1.5 text-surface-600 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="New Worksheet">
          <Upload className="w-3.5 h-3.5" />
          <span className="hidden md:inline">New</span>
        </button>
        <button onClick={() => setShowExportModal(true)}
          className="text-xs flex items-center gap-1 px-2 py-1.5 text-surface-600 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="Export (Ctrl+E)">
          <Download className="w-3.5 h-3.5" />
          <span className="hidden md:inline">Export</span>
        </button>
      </div>

      {/* Center: Save / Discard + Undo/Redo */}
      <div className="flex items-center gap-1">
        <button onClick={saveChanges} disabled={!hasUnsavedChanges} title="Save (Ctrl+S)"
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
            hasUnsavedChanges
              ? 'bg-brand-orange hover:bg-brand-orange-dark text-white shadow-sm'
              : 'bg-surface-100 text-surface-400 cursor-not-allowed border border-surface-200'
          }`}>
          <Save className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Save</span>
          {hasUnsavedChanges && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
        </button>

        <button onClick={discardChanges} disabled={!hasUnsavedChanges} title="Discard Changes"
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            hasUnsavedChanges
              ? 'bg-red-50 hover:bg-red-100 text-danger-500 border border-red-200'
              : 'bg-surface-100 text-surface-400 cursor-not-allowed border border-surface-200'
          }`}>
          <RotateCcw className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Discard</span>
        </button>

        <div className="w-px h-5 bg-surface-200 mx-0.5" />

        <button onClick={handleUndo} className="p-1.5 text-surface-500 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="Undo (Ctrl+Z)">
          <Undo2 className="w-4 h-4" />
        </button>
        <button onClick={handleRedo} className="p-1.5 text-surface-500 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="Redo (Ctrl+Shift+Z)">
          <Redo2 className="w-4 h-4" />
        </button>

        <div className="w-px h-5 bg-surface-200 mx-0.5" />

        <button onClick={() => setShowGrid(!showGrid)}
          className={`p-1.5 rounded-lg transition-all ${showGrid ? 'text-brand-orange bg-accent-50' : 'text-surface-500 hover:text-surface-900 hover:bg-surface-100'}`}
          title="Toggle Grid">
          <Grid3x3 className="w-4 h-4" />
        </button>
      </div>

      {/* Right: Zoom controls */}
      <div className="flex items-center gap-1">
        {hasUnsavedChanges && (
          <span className="text-[10px] text-brand-orange font-medium hidden lg:flex items-center gap-1 mr-1">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-orange animate-pulse" />
            Unsaved
          </span>
        )}

        <button onClick={zoomOut} className="p-1.5 text-surface-500 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="Zoom Out">
          <ZoomOut className="w-3.5 h-3.5" />
        </button>

        <input type="range" min="25" max="200" value={Math.round(zoom * 100)}
          onChange={(e) => setZoom(parseInt(e.target.value) / 100)}
          className="w-20 h-1.5 rounded-full appearance-none cursor-pointer
                     [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                     [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-orange [&::-webkit-slider-thumb]:shadow-sm
                     [&::-webkit-slider-thumb]:cursor-pointer"
          style={{ background: `linear-gradient(to right, #F57C00 0%, #F57C00 ${((zoom*100-25)/175)*100}%, #E0E0E0 ${((zoom*100-25)/175)*100}%, #E0E0E0 100%)` }}
        />

        <div className="relative group">
          <button className="text-[11px] text-surface-600 hover:text-surface-900 w-11 text-center font-medium py-1 rounded hover:bg-surface-100 transition-all cursor-pointer"
            title="Click for zoom presets">
            {Math.round(zoom * 100)}%
          </button>
          <div className="absolute top-full right-0 mt-1 bg-white border border-surface-200 rounded-lg shadow-lg py-1 hidden group-hover:block z-50 min-w-[70px]">
            {zoomPresets.map(p => (
              <button key={p} onClick={() => setZoom(p / 100)}
                className={`w-full text-left px-3 py-1 text-xs hover:bg-surface-100 transition-colors ${
                  Math.round(zoom*100) === p ? 'text-brand-orange font-medium' : 'text-surface-600'}`}>
                {p}%
              </button>
            ))}
          </div>
        </div>

        <button onClick={zoomIn} className="p-1.5 text-surface-500 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="Zoom In">
          <ZoomIn className="w-3.5 h-3.5" />
        </button>

        <div className="w-px h-5 bg-surface-200" />

        <button onClick={handleFitToScreen} className="p-1.5 text-surface-500 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all" title="Fit to Screen">
          <Maximize className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
