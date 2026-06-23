import { useCallback, useMemo, useState } from 'react';
import { X, Download, FileCode, Printer, FileText, FolderOpen, Loader2, CheckCircle2 } from 'lucide-react';
import useWorksheetStore from '../../store/worksheetStore';
import useAuthStore from '../../store/authStore';

export default function ExportModal() {
  const originalHTML = useWorksheetStore((s) => s.originalHTML);
  const draftHTML = useWorksheetStore((s) => s.draftHTML);
  const hasUnsavedChanges = useWorksheetStore((s) => s.hasUnsavedChanges);
  const worksheetMeta = useWorksheetStore((s) => s.worksheetMeta);
  const setShowExportModal = useWorksheetStore((s) => s.setShowExportModal);
  const readOnly = useWorksheetStore((s) => s.readOnly);
  const token = useAuthStore((s) => s.token);

  const [fileName, setFileName] = useState((worksheetMeta.title || 'worksheet').trim());
  const [activityName, setActivityName] = useState('');
  const [s3Status, setS3Status] = useState('');
  const [s3Error, setS3Error] = useState('');
  const [isSavingToS3, setIsSavingToS3] = useState(false);
  const [isGeneratingPDF, setIsGeneratingPDF] = useState(false);

  const currentHTML = useMemo(() => (
    (hasUnsavedChanges && draftHTML) ? draftHTML : originalHTML
  ), [draftHTML, hasUnsavedChanges, originalHTML]);

  // ──────────────────────────────────────────────────────────────
  //  DYNAMIC PDF EXPORT ENGINE
  //  Strategy: Render → Measure → Scale → Print
  //  Guarantees single-page A4 with footer pinned to bottom.
  // ──────────────────────────────────────────────────────────────

  // Extract body innerHTML from stored full-document HTML
  const extractBodyContent = useCallback((html) => {
    const match = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
    return match ? match[1] : html;
  }, []);

  // Build the print-ready HTML document
  const buildPrintDocument = useCallback(() => {
    const bodyContent = extractBodyContent(currentHTML);

    // Extract font links
    const fontLinks = [];
    const linkRe = /<link[^>]*href="[^"]*fonts[^"]*"[^>]*>/gi;
    let m;
    while ((m = linkRe.exec(currentHTML)) !== null) fontLinks.push(m[0]);

    // Extract template styles (skip editor styles)
    const styleRe = /<style(?:(?!id="ws-editor)[^>])*>([\s\S]*?)<\/style>/gi;
    const styles = [];
    while ((m = styleRe.exec(originalHTML)) !== null) styles.push(m[1]);

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
${fontLinks.join('\n')}
<style>
${styles.join('\n')}
</style>
<style id="ws-export-fix">
/* ═══ EXPORT ENGINE: Exact A4 single-page layout ═══ */
*, *::before, *::after { box-sizing: border-box; }
@page { size: A4; margin: 0; }
html {
  width: 210mm;
  height: 297mm;
  margin: 0; padding: 0;
  overflow: hidden;
}
body {
  width: 210mm;
  height: 297mm;
  margin: 0; padding: 0;
  background: white;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
  overflow: hidden;
}
/* Page fills exactly one A4 — flex column pins footer to bottom */
.ws-page {
  width: 210mm !important;
  height: 297mm !important;
  min-height: 0 !important;
  max-height: 297mm !important;
  margin: 0 !important;
  padding: 0 !important;
  box-shadow: none !important;
  border: none !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
}
.ws-header {
  flex-shrink: 0 !important;
}
.ws-body {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow: hidden !important;
}
.ws-footer {
  flex-shrink: 0 !important;
  width: 100% !important;
  padding: 3mm 8mm 5mm 8mm !important;
  margin-top: auto !important;
  display: flex !important;
  flex-direction: row !important;
  justify-content: flex-end !important;
  align-items: center !important;
  gap: 24px !important;
  box-sizing: border-box !important;
}
.ws-footer-text, .footer-text {
  font-size: 10px !important;
  font-weight: 400 !important;
  white-space: nowrap !important;
}
.ws-vertical-copyright, .vertical-copyright {
  left: -193px !important;
}
</style>
</head>
<body>
${bodyContent}
</body>
</html>`;
  }, [currentHTML, extractBodyContent]);

  // ── SERVER-SIDE PDF EXPORT: Guarantees true A4 (595×842pt) via Puppeteer ──
  const handleExportPDF = useCallback(async () => {
    setIsGeneratingPDF(true);
    try {
      const response = await fetch('/api/worksheets/generate-pdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          html: currentHTML,
          fileName: fileName || 'worksheet',
        }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.message || 'PDF generation failed');
      }

      // Download the PDF
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(fileName || 'worksheet').replace(/[^a-zA-Z0-9._-]/g, '-')}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setShowExportModal(false);
    } catch (error) {
      console.error('PDF export failed:', error);
      alert('PDF generation failed: ' + error.message);
    } finally {
      setIsGeneratingPDF(false);
    }
  }, [currentHTML, fileName, token, setShowExportModal]);

  // ── BROWSER PRINT: Uses system print dialog with A4 CSS hints ──
  const handlePrint = useCallback(() => {
    const html = buildPrintDocument();

    const printFrame = document.createElement('iframe');
    printFrame.style.cssText =
      'position:fixed; left:-9999px; top:0; width:210mm; height:297mm; border:none;';
    document.body.appendChild(printFrame);

    const pDoc = printFrame.contentDocument || printFrame.contentWindow.document;
    pDoc.open();
    pDoc.write(html);
    pDoc.close();

    let printed = false;
    const triggerPrint = () => {
      if (printed) return;
      printed = true;
      setTimeout(() => {
        try {
          printFrame.contentWindow.focus();
          printFrame.contentWindow.print();
        } catch (e) {
          console.error('Print error:', e);
        }
        setTimeout(() => {
          try { document.body.removeChild(printFrame); } catch (e) {}
        }, 5000);
      }, 600);
    };

    printFrame.onload = triggerPrint;
    setTimeout(triggerPrint, 3000);
    setShowExportModal(false);
  }, [buildPrintDocument, setShowExportModal]);

  // ── HTML Download ──
  const handleExportHTML = useCallback(() => {
    const html = currentHTML;
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'worksheet.html';
    a.click();
    URL.revokeObjectURL(url);
    setShowExportModal(false);
  }, [currentHTML, setShowExportModal]);

  // ── Save to S3 (HTML + PDF pair) ──
  const handleSaveToS3 = useCallback(async () => {
    setS3Error('');
    setS3Status('');
    setIsSavingToS3(true);

    try {
      const response = await fetch('/api/worksheets/s3', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          html: currentHTML,
          fileName,
          activityName: activityName || 'general',
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || data.error || 'Failed to save to S3');
      }

      setS3Status(
        data.pdfLocation
          ? `Saved HTML + PDF to ${data.htmlLocation}`
          : `Saved HTML to ${data.htmlLocation} (PDF generation pending)`
      );
    } catch (error) {
      setS3Error(error.message || 'Failed to save to S3');
    } finally {
      setIsSavingToS3(false);
    }
  }, [currentHTML, fileName, activityName, token]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in"
         onClick={(e) => { if (e.target === e.currentTarget) setShowExportModal(false); }}>
      <div className="bg-white border border-surface-200 rounded-2xl p-6 w-full max-w-md shadow-2xl animate-slide-up">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-surface-900">Export Worksheet</h2>
          <button onClick={() => setShowExportModal(false)}
            className="p-1.5 text-surface-400 hover:text-surface-700 hover:bg-surface-100 rounded-lg transition-all">
            <X className="w-4 h-4" />
          </button>
        </div>

        {hasUnsavedChanges && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-accent-50 border border-accent-100 text-xs text-brand-orange">
            ⚠ You have unsaved changes. The export will include your latest edits.
          </div>
        )}

        {/* S3 Upload Section — owner only (hidden for read-only viewers) */}
        {!readOnly && (
        <div className="mb-4 space-y-3 rounded-xl border border-surface-200 bg-surface-50 p-4">
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-surface-500">File Name</label>
            <input
              value={fileName}
              onChange={(e) => setFileName(e.target.value)}
              className="input-field w-full text-xs"
              placeholder="worksheet-name"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-surface-500">
              <span className="flex items-center gap-1">
                <FolderOpen className="w-3 h-3" />
                Activity Name
              </span>
            </label>
            <input
              value={activityName}
              onChange={(e) => setActivityName(e.target.value)}
              className="input-field w-full text-xs"
              placeholder="e.g., Addition Two Digits"
            />
            <p className="mt-1 text-[10px] text-surface-400">
              Creates a folder in S3 with this name. Both HTML and PDF will be stored together.
            </p>
          </div>
          <button
            onClick={handleSaveToS3}
            disabled={isSavingToS3 || !currentHTML.trim()}
            className="w-full rounded-xl bg-brand-orange px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-brand-orange-dark disabled:cursor-not-allowed disabled:bg-surface-300 flex items-center justify-center gap-2"
          >
            {isSavingToS3 ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating PDF & Saving...
              </>
            ) : (
              'Save to S3 (HTML + PDF)'
            )}
          </button>
          {s3Status && (
            <div className="flex items-start gap-2 text-xs text-success-500">
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>{s3Status}</span>
            </div>
          )}
          {s3Error && <p className="text-xs text-danger-500">{s3Error}</p>}
        </div>
        )}

        {/* Export Buttons */}
        <div className="space-y-2.5">
          <button onClick={handleExportPDF}
            disabled={isGeneratingPDF}
            className="w-full flex items-center gap-4 p-4 rounded-xl bg-surface-50 hover:bg-accent-50
                       border border-surface-200 hover:border-brand-orange/30 transition-all duration-200 group
                       disabled:opacity-60 disabled:cursor-wait">
            <div className="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
              {isGeneratingPDF ? (
                <Loader2 className="w-5 h-5 text-danger-500 animate-spin" />
              ) : (
                <FileText className="w-5 h-5 text-danger-500" />
              )}
            </div>
            <div className="text-left">
              <p className="text-sm font-medium text-surface-900">
                {isGeneratingPDF ? 'Generating PDF...' : 'Export as PDF'}
              </p>
              <p className="text-xs text-surface-500">A4 format • 210mm × 297mm</p>
            </div>
            <Download className="w-4 h-4 text-surface-400 ml-auto group-hover:text-brand-orange transition-colors" />
          </button>

          <button onClick={handlePrint}
            className="w-full flex items-center gap-4 p-4 rounded-xl bg-surface-50 hover:bg-purple-50
                       border border-surface-200 hover:border-purple-300 transition-all duration-200 group">
            <div className="w-10 h-10 rounded-lg bg-purple-50 flex items-center justify-center">
              <Printer className="w-5 h-5 text-purple-600" />
            </div>
            <div className="text-left">
              <p className="text-sm font-medium text-surface-900">Print</p>
              <p className="text-xs text-surface-500">Send directly to printer</p>
            </div>
            <Printer className="w-4 h-4 text-surface-400 ml-auto group-hover:text-purple-600 transition-colors" />
          </button>

          <div className="w-full h-px bg-surface-200 my-1" />

          <button onClick={handleExportHTML}
            className="w-full flex items-center gap-4 p-4 rounded-xl bg-surface-50 hover:bg-blue-50
                       border border-surface-200 hover:border-blue-300 transition-all duration-200 group">
            <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
              <FileCode className="w-5 h-5 text-blue-600" />
            </div>
            <div className="text-left">
              <p className="text-sm font-medium text-surface-900">Export as HTML</p>
              <p className="text-xs text-surface-500">Download clean HTML file</p>
            </div>
            <Download className="w-4 h-4 text-surface-400 ml-auto group-hover:text-blue-600 transition-colors" />
          </button>
        </div>

        <p className="text-[10px] text-surface-400 mt-4 text-center">
          A4 format • 210mm × 297mm • Server-side generation
        </p>
      </div>
    </div>
  );
}
