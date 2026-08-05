import { useState, useCallback, useRef, useEffect } from 'react';
import { AlertCircle, ArrowRight, ArrowLeft, Clipboard, Trash2 } from 'lucide-react';
import useWorksheetStore from '../../store/worksheetStore';
import { parseHTMLString } from '../../engine/htmlParser';
import { detectBlocks } from '../../engine/detectionEngine';
import { wrapInSinhalaTemplate } from '../../engine/sinhalaTemplateWrapper';

export default function SinhalaUploadScreen() {
  const rawHTML = useWorksheetStore((s) => s.rawHTML);
  const setRawHTML = useWorksheetStore((s) => s.setRawHTML);
  const [htmlInput, setHtmlInput] = useState(rawHTML || '');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef(null);

  // Sync htmlInput when rawHTML changes (e.g. returning from editor with modifications)
  useEffect(() => {
    if (rawHTML) setHtmlInput(rawHTML);
  }, [rawHTML]);

  const setView = useWorksheetStore((s) => s.setView);
  const setBlocks = useWorksheetStore((s) => s.setBlocks);
  const setOriginalHTML = useWorksheetStore((s) => s.setOriginalHTML);
  const setWorksheetMeta = useWorksheetStore((s) => s.setWorksheetMeta);
  const setReadOnly = useWorksheetStore((s) => s.setReadOnly);
  const setWorksheetLang = useWorksheetStore((s) => s.setWorksheetLang);

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
      setError("මෙය නිවැරදි HTML ලෙස පෙනෙන්නේ නැත. සම්පූර්ණ HTML වැඩ පත්‍රිකාවක් ඇලවන්න.");
      return;
    }
    setLoading(true);
    setError('');
    setRawHTML(htmlInput);
    setWorksheetLang('si');
    try {
      const wrappedHTML = wrapInSinhalaTemplate(htmlInput);
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
  }, [htmlInput, isValidHTML, setOriginalHTML, setBlocks, setWorksheetMeta, setView, setReadOnly, setWorksheetLang]);

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
              title="උපකරණ පුවරුවට ආපසු"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <img src="/gb-logo.jpg" alt="GeniusBees" className="h-9 object-contain" />
            <div className="w-px h-7 bg-surface-200" />
            <div>
              <h1 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
                සිංහල වැඩ පත්‍රිකා සංස්කාරකය
                <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 border border-amber-200 rounded text-[9px] font-semibold uppercase">සිංහල</span>
              </h1>
              <p className="text-[10px] text-surface-500">සංස්කරණය ආරම්භ කිරීමට පහත HTML ඇලවන්න</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handlePasteFromClipboard}
              className="text-xs flex items-center gap-1.5 px-3 py-1.5 text-surface-600 hover:text-surface-900 hover:bg-surface-100 rounded-lg transition-all border border-surface-200"
              title="ක්ලිප්බෝඩ් එකෙන් ඇලවන්න">
              <Clipboard className="w-3.5 h-3.5" /> ඇලවන්න
            </button>
            {hasHTML && (
              <button onClick={handleClear}
                className="text-xs flex items-center gap-1.5 px-3 py-1.5 text-danger-500 hover:bg-red-50 rounded-lg transition-all border border-red-200">
                <Trash2 className="w-3.5 h-3.5" /> මකන්න
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
            placeholder={`ඔබගේ HTML වැඩ පත්‍රිකා කේතය මෙහි ඇලවන්න...\n\nඋදාහරණය:\n<!DOCTYPE html>\n<html>\n<head>...</head>\n<body>\n  <div class="worksheet">\n    ...\n  </div>\n</body>\n</html>`}
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

        {/* Open in Editor Button */}
        <div className="px-4 py-3 border-t border-surface-200 shrink-0">
          <button
            onClick={handleProceedToEditor}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all duration-200 shadow-md active:scale-[0.98] bg-brand-orange hover:bg-brand-orange-dark text-white"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                HTML විග්‍රහ කරමින්...
              </>
            ) : (
              <>
                සංස්කාරකයේ විවෘත කරන්න
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
            <span className="text-xs font-medium text-surface-600">සජීවී පෙරදසුන</span>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {hasHTML ? (
            <div className="bg-white rounded-xl shadow-md overflow-hidden animate-fade-in border border-surface-200">
              <iframe
                srcDoc={htmlInput}
                title="වැඩ පත්‍රිකා පෙරදසුන"
                className="w-full border-none"
                style={{ minHeight: '500px', height: 'calc(100vh - 140px)' }}
                sandbox="allow-same-origin"
              />
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <img src="/gb-logo.jpg" alt="GeniusBees" className="h-16 object-contain mb-4 opacity-40" />
              <p className="text-surface-700 text-sm font-medium mb-1">තවමත් පෙරදසුනක් නොමැත</p>
              <p className="text-surface-500 text-xs max-w-xs">
                ඔබගේ වැඩ පත්‍රිකාවේ සජීවී පෙරදසුනක් මෙහි බැලීමට වම් පැනලයේ HTML කේතය ඇලවන්න
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
