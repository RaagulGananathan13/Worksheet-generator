import { useRef, useEffect, useState } from 'react';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import useWorksheetStore from '../../store/worksheetStore';
import Toolbar from '../Toolbar/Toolbar';
import Canvas from '../Canvas/Canvas';
import PropertyPanel from '../PropertyPanel/PropertyPanel';
import ExportModal from '../ExportModal/ExportModal';

export default function EditorLayout() {
  const containerRef = useRef(null);
  const showExportModal = useWorksheetStore((s) => s.showExportModal);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelWidth, setPanelWidth] = useState(300);
  const isResizing = useRef(false);

  // Prevent browser native zoom globally
  useEffect(() => {
    const preventNativeZoom = (e) => {
      if (e.ctrlKey || e.metaKey) e.preventDefault();
    };
    document.addEventListener('wheel', preventNativeZoom, { passive: false });
    return () => document.removeEventListener('wheel', preventNativeZoom);
  }, []);

  // Panel resize drag
  const startResize = (e) => {
    isResizing.current = true;
    const startX = e.clientX;
    const startWidth = panelWidth;

    const onMouseMove = (e) => {
      if (!isResizing.current) return;
      const delta = startX - e.clientX;
      const newWidth = Math.max(240, Math.min(450, startWidth + delta));
      setPanelWidth(newWidth);
    };

    const onMouseUp = () => {
      isResizing.current = false;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  };

  return (
    <div className="h-full flex flex-col bg-surface-100">
      {/* Top Toolbar */}
      <Toolbar />

      {/* Main Area: Canvas + Property Panel */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Canvas */}
        <div ref={containerRef} className="flex-1 relative overflow-hidden">
          <Canvas containerRef={containerRef} />
        </div>

        {/* Panel toggle button */}
        <button
          onClick={() => setPanelOpen(!panelOpen)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-30 bg-white border border-surface-200 rounded-l-lg p-1.5 shadow-md
                     text-surface-500 hover:text-brand-orange hover:border-brand-orange/30 transition-all"
          style={{ right: panelOpen ? panelWidth : 0 }}
          title={panelOpen ? 'Collapse panel' : 'Expand panel'}>
          {panelOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
        </button>

        {/* Resize handle + Property Panel */}
        {panelOpen && (
          <>
            {/* Resize handle */}
            <div
              onMouseDown={startResize}
              className="w-1 hover:w-1.5 bg-surface-200 hover:bg-brand-orange/40 cursor-col-resize transition-all shrink-0"
              title="Drag to resize panel"
            />
            {/* Right Property Panel */}
            <div style={{ width: panelWidth }} className="shrink-0 overflow-hidden transition-all duration-200">
              <PropertyPanel />
            </div>
          </>
        )}
      </div>

      {/* Export Modal */}
      {showExportModal && <ExportModal />}
    </div>
  );
}
