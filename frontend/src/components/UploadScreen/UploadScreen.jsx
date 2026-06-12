import { useState, useCallback, useRef } from 'react';
import { AlertCircle, ArrowRight, ArrowLeft, Clipboard, Trash2 } from 'lucide-react';
import useWorksheetStore from '../../store/worksheetStore';
import { parseHTMLString } from '../../engine/htmlParser';
import { detectBlocks } from '../../engine/detectionEngine';
import { wrapInTemplate } from '../../engine/templateWrapper';

export default function UploadScreen() {
  const [htmlInput, setHtmlInput] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef(null);

  const setView = useWorksheetStore((s) => s.setView);
  const setBlocks = useWorksheetStore((s) => s.setBlocks);
  const setOriginalHTML = useWorksheetStore((s) => s.setOriginalHTML);
  const setWorksheetMeta = useWorksheetStore((s) => s.setWorksheetMeta);
  const setReadOnly = useWorksheetStore((s) => s.setReadOnly);

  const isValidHTML = useCallback((str) => {
    const trimmed = str.trim();
    return trimmed.startsWith('<') || trimmed.includes('<!DOCTYPE') || trimmed.includes('<html');
  }, []);

  const handlePasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) { setHtmlInput(text); setError(''); }
    } catch {
      textareaRef.current?.focus();
    }
  }, []);

  const handleInputChange = useCallback((e) => {
    setHtmlInput(e.target.value);
    setError('');
  }, []);

  const handleClear = useCallback(() => {
    setHtmlInput('');
    setError('');
  }, []);

  const handleProceedToEditor = useCallback(async () => {
    if (htmlInput.trim() && !isValidHTML(htmlInput)) {
      setError("This doesn't look like valid HTML. Please paste a complete HTML worksheet.");
      return;
    }
    setLoading(true);
    setError('');
    try {
      const wrappedHTML = wrapInTemplate(htmlInput);
      setOriginalHTML(wrappedHTML);
      const { elements, worksheetMeta } = await parseHTMLString(wrappedHTML);
      const blocks = detectBlocks(elements, worksheetMeta);
      
      setBlocks(blocks);
      setWorksheetMeta(worksheetMeta);
      setReadOnly(false);
      setView('editor');
    } catch (err) {
      setError(`Parsing failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [htmlInput, isValidHTML, setOriginalHTML, setBlocks, setWorksheetMeta, setView, setReadOnly]);

  const hasHTML = htmlInput.trim().length > 0;

  return (
    <div className="h-full flex animate-fade-in bg-white">
      {/* Left Panel */}
      <div className="w-1/2 flex flex-col border-r border-surface-200">
        {/* Header with GB Logo */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-surface-200 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setView('dashboard')}
              className="p-1.5 text-surface-400 hover:text-brand-orange hover:bg-accent-50 rounded-lg transition-all"
              title="Back to Dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <img src="/gb-logo.jpg" alt="GeniusBees" className="h-9 object-contain" />
            <div className="w-px h-7 bg-surface-200" />
            <div>
              <h1 className="text-sm font-semibold text-surface-900">Worksheet Editor</h1>
              <p className="text-[10px] text-surface-500">Paste HTML below to start editing</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handlePasteFromClipboard}
              className="text-xs flex items-center gap-1.5 px-3 py-1.5 text-surface-600 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all border border-surface-200"
              title="Paste from clipboard">
              <Clipboard className="w-3.5 h-3.5" /> Paste
            </button>
            {hasHTML && (
              <button onClick={handleClear}
                className="text-xs flex items-center gap-1.5 px-3 py-1.5 text-danger-500 hover:bg-red-50 rounded-lg transition-all border border-red-200">
                <Trash2 className="w-3.5 h-3.5" /> Clear
              </button>
            )}
          </div>
        </div>

        {/* Textarea */}
        <div className="flex-1 overflow-auto p-4">
          <textarea
            ref={textareaRef}
            value={htmlInput}
            onChange={handleInputChange}
            placeholder={`Paste your HTML worksheet code here...\n\nExample:\n<!DOCTYPE html>\n<html>\n<head>...</head>\n<body>\n  <div class="worksheet">\n    ...\n  </div>\n</body>\n</html>`}
            className="w-full h-full min-h-[300px] bg-surface-50 border border-surface-200 rounded-xl p-4 text-sm text-surface-800 font-mono
                       placeholder:text-surface-400 resize-none
                       focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/40
                       transition-all duration-200"
            spellCheck={false}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mb-3 px-4 py-2.5 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2 text-danger-500 text-xs animate-fade-in">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Open in Editor Button — ALWAYS VISIBLE */}
        <div className="px-4 py-3 border-t border-surface-200 shrink-0">
          <button
            onClick={handleProceedToEditor}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all duration-200 shadow-md active:scale-[0.98] bg-brand-orange hover:bg-brand-orange-dark text-white"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Parsing HTML...
              </>
            ) : (
              <>
                Open in Editor
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Right Panel: Live Preview */}
      <div className="w-1/2 flex flex-col bg-surface-50">
        <div className="flex items-center px-5 py-3 border-b border-surface-200 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-brand-green animate-pulse-soft" />
            <span className="text-xs font-medium text-surface-600">Live Preview</span>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {hasHTML ? (
            <div className="bg-white rounded-xl shadow-md overflow-hidden animate-fade-in border border-surface-200">
              <iframe
                srcDoc={htmlInput}
                title="Worksheet Preview"
                className="w-full border-none"
                style={{ minHeight: '500px', height: 'calc(100vh - 140px)' }}
                sandbox="allow-same-origin"
              />
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <img src="/gb-logo.jpg" alt="GeniusBees" className="h-16 object-contain mb-4 opacity-40" />
              <p className="text-surface-700 text-sm font-medium mb-1">No preview yet</p>
              <p className="text-surface-500 text-xs max-w-xs">
                Paste HTML code in the left panel to see a live preview of your worksheet here
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
