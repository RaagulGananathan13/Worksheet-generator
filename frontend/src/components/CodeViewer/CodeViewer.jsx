import { useMemo } from 'react';
import { X, Copy, CheckCircle2 } from 'lucide-react';
import { useState } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Code Viewer Modal — Shows the raw HTML source of the worksheet.
 * Available for read-only viewers to inspect the HTML structure.
 */
export default function CodeViewer() {
  const originalHTML = useWorksheetStore((s) => s.originalHTML);
  const draftHTML = useWorksheetStore((s) => s.draftHTML);
  const setShowCodeViewer = useWorksheetStore((s) => s.setShowCodeViewer);
  const [copied, setCopied] = useState(false);

  const html = useMemo(() => draftHTML || originalHTML, [draftHTML, originalHTML]);

  // Format the HTML with basic indentation
  const formattedHTML = useMemo(() => {
    if (!html) return '';
    try {
      let formatted = html;
      // Basic formatting: add newlines after closing tags
      formatted = formatted.replace(/></g, '>\n<');
      // Indent based on nesting level
      const lines = formatted.split('\n');
      let indent = 0;
      return lines.map((line) => {
        const trimmed = line.trim();
        if (!trimmed) return '';
        // Decrease indent for closing tags
        if (trimmed.startsWith('</')) indent = Math.max(0, indent - 1);
        const result = '  '.repeat(indent) + trimmed;
        // Increase indent for opening tags (not self-closing, not closing)
        if (trimmed.startsWith('<') && !trimmed.startsWith('</') && !trimmed.endsWith('/>') && !trimmed.includes('</')) {
          indent++;
        }
        return result;
      }).filter(Boolean).join('\n');
    } catch {
      return html;
    }
  }, [html]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(html);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = html;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) setShowCodeViewer(false); }}
    >
      <div className="bg-white border border-surface-200 rounded-2xl w-full max-w-4xl max-h-[85vh] shadow-2xl animate-slide-up flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-200">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-purple-50 flex items-center justify-center">
              <span className="text-purple-600 text-sm font-mono">&lt;/&gt;</span>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-surface-900">HTML Source</h2>
              <p className="text-xs text-surface-500">View the worksheet HTML code</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                copied
                  ? 'bg-green-50 text-green-600 border border-green-200'
                  : 'bg-surface-100 text-surface-600 hover:bg-surface-200 border border-surface-200'
              }`}
            >
              {copied ? (
                <><CheckCircle2 className="w-3.5 h-3.5" /> Copied!</>
              ) : (
                <><Copy className="w-3.5 h-3.5" /> Copy HTML</>
              )}
            </button>
            <button
              onClick={() => setShowCodeViewer(false)}
              className="p-1.5 text-surface-400 hover:text-surface-700 hover:bg-surface-100 rounded-lg transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Code content */}
        <div className="flex-1 overflow-auto p-4">
          <pre className="text-xs font-mono leading-relaxed text-surface-700 bg-surface-50 rounded-xl p-4 border border-surface-200 overflow-x-auto whitespace-pre-wrap break-words">
            {formattedHTML || 'No HTML content available.'}
          </pre>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-surface-200 flex items-center justify-between">
          <span className="text-[10px] text-surface-400">
            {html ? `${html.length.toLocaleString()} characters` : ''}
          </span>
          <button
            onClick={() => setShowCodeViewer(false)}
            className="px-4 py-1.5 text-xs font-medium text-surface-600 bg-surface-100 hover:bg-surface-200 rounded-lg transition-all border border-surface-200"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
