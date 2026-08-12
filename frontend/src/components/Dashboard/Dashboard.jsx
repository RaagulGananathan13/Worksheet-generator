import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Search, FileText, Trash2, Eye, Calendar, User,
  FolderOpen, Loader2, LogOut, RefreshCw, AlertCircle, RotateCcw
} from 'lucide-react';
import useAuthStore from '../../store/authStore';
import useWorksheetStore from '../../store/worksheetStore';
import { parseHTMLString } from '../../engine/htmlParser';
import { detectBlocks } from '../../engine/detectionEngine';

export default function Dashboard() {
  const [worksheets, setWorksheets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [viewingId, setViewingId] = useState(null);

  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const setView = useWorksheetStore((s) => s.setView);
  const setOriginalHTML = useWorksheetStore((s) => s.setOriginalHTML);
  const setBlocks = useWorksheetStore((s) => s.setBlocks);
  const setWorksheetMeta = useWorksheetStore((s) => s.setWorksheetMeta);
  const setReadOnly = useWorksheetStore((s) => s.setReadOnly);

  // Session recovery state
  const savedDraftHTML = useWorksheetStore((s) => s.draftHTML);
  const savedOriginalHTML = useWorksheetStore((s) => s.originalHTML);
  const savedLang = useWorksheetStore((s) => s.worksheetLang);
  const clearSession = useWorksheetStore((s) => s.clearSession);
  const hasSavedSession = !!(savedDraftHTML || savedOriginalHTML);

  const handleResumeSession = useCallback(() => {
    // Restore the editor view — the persist middleware already has all the data
    setView('editor');
  }, [setView]);

  const handleDismissSession = useCallback(() => {
    clearSession();
  }, [clearSession]);

  // ─── Fetch worksheets ──────────────────────────────────
  // S3 DISABLED (AWS cost reduction) — skip fetching from S3
  // To re-enable, uncomment the fetch block below

  const fetchWorksheets = useCallback(async () => {
    setLoading(true);
    setError('');
    // S3 fetch disabled — always return empty list
    // try {
    //   const res = await fetch('/api/worksheets', {
    //     headers: { Authorization: `Bearer ${token}` },
    //   });
    //   if (!res.ok) throw new Error('Failed to load worksheets');
    //   const data = await res.json();
    //   setWorksheets(data.worksheets || []);
    // } catch (err) {
    //   setError(err.message || 'Failed to load worksheets.');
    // }
    setWorksheets([]);
    setLoading(false);
  }, [token]);

  useEffect(() => {
    fetchWorksheets();
  }, [fetchWorksheets]);

  // ─── View worksheet ────────────────────────────────────

  const handleView = useCallback(
    async (id) => {
      setViewingId(id);
      try {
        const res = await fetch(`/api/worksheets/${id}/content`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.message || 'Failed to load worksheet');
        }
        const data = await res.json();
        const html = data.html;

        // Load HTML into the editor
        setOriginalHTML(html);
        const { elements, worksheetMeta } = await parseHTMLString(html);
        const blocks = detectBlocks(elements, worksheetMeta);
        setBlocks(blocks);
        setWorksheetMeta({
          ...worksheetMeta,
          title: data.worksheet.fileName || worksheetMeta.title,
        });
        setReadOnly(!data.worksheet.isOwner);
        setView('editor');
      } catch (err) {
        alert(err.message || 'Failed to load worksheet content.');
      } finally {
        setViewingId(null);
      }
    },
    [token, setOriginalHTML, setBlocks, setWorksheetMeta, setView, setReadOnly]
  );

  // ─── Delete worksheet ──────────────────────────────────

  const handleDelete = useCallback(
    async (id, name) => {
      if (!window.confirm(`Delete "${name}"? This will remove both HTML and PDF from S3.`)) return;
      setDeletingId(id);
      try {
        const res = await fetch(`/api/worksheets/${id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.message || 'Failed to delete');
        }
        setWorksheets((prev) => prev.filter((w) => w.id !== id));
      } catch (err) {
        alert(err.message);
      } finally {
        setDeletingId(null);
      }
    },
    [token]
  );

  // ─── Filter worksheets ────────────────────────────────

  const filtered = worksheets.filter((w) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      w.fileName.toLowerCase().includes(q) ||
      w.activityName.toLowerCase().includes(q) ||
      w.ownerEmail.toLowerCase().includes(q)
    );
  });

  const myWorksheets = filtered.filter((w) => w.isOwner);
  const othersWorksheets = filtered.filter((w) => !w.isOwner);

  // ─── Logout handler ────────────────────────────────────

  const handleLogout = useCallback(() => {
    logout();
    setView('auth');
  }, [logout, setView]);

  return (
    <div className="h-full flex flex-col bg-gradient-to-br from-surface-50 via-white to-accent-50/30 animate-fade-in">
      {/* ─── Header ─────────────────────────────────────── */}
      <div className="shrink-0 bg-white/80 backdrop-blur-sm border-b border-surface-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/gb-logo.jpg" alt="GeniusBees" className="h-9 object-contain" />
            <div className="w-px h-7 bg-surface-200" />
            <div>
              <h1 className="text-sm font-semibold text-surface-900">Worksheet Dashboard</h1>
              <p className="text-[10px] text-surface-500">Manage your worksheets</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-surface-50 rounded-lg border border-surface-200">
              <User className="w-3.5 h-3.5 text-surface-400" />
              <span className="text-xs text-surface-600 font-medium">{user?.email}</span>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-surface-600 hover:text-danger-500 hover:bg-red-50 rounded-lg border border-surface-200 hover:border-red-200 transition-all"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </div>

      {/* ─── Actions Bar ────────────────────────────────── */}
      <div className="shrink-0 max-w-7xl w-full mx-auto px-6 pt-6 pb-3">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-surface-900">Your Worksheets</h2>
            <p className="text-xs text-surface-500 mt-0.5">
              {worksheets.length} total • {myWorksheets.length} yours
            </p>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            {/* Search */}
            <div className="relative flex-1 sm:flex-initial">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search worksheets..."
                className="w-full sm:w-64 pl-9 pr-4 py-2 bg-white border border-surface-200 rounded-xl text-sm text-surface-900
                           placeholder:text-surface-400
                           focus:outline-none focus:ring-2 focus:ring-brand-orange/20 focus:border-brand-orange/40
                           transition-all duration-200"
              />
            </div>

            {/* Refresh */}
            <button
              onClick={fetchWorksheets}
              disabled={loading}
              className="p-2 text-surface-500 hover:text-surface-900 hover:bg-surface-100 rounded-xl border border-surface-200 transition-all"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            {/* Create New (English) */}
            <button
              onClick={() => { useWorksheetStore.getState().setWorksheetLang('en'); setView('upload'); }}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-brand-orange to-brand-orange-dark text-white text-sm font-semibold rounded-xl
                         shadow-md shadow-brand-orange/20 hover:shadow-lg hover:shadow-brand-orange/30
                         transition-all duration-300 active:scale-[0.98]"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">Create New</span>
            </button>

            {/* Create New (Sinhala) */}
            <button
              onClick={() => { useWorksheetStore.getState().setWorksheetLang('si'); setView('upload-sinhala'); }}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 text-white text-sm font-semibold rounded-xl
                         shadow-md shadow-amber-500/20 hover:shadow-lg hover:shadow-amber-500/30
                         transition-all duration-300 active:scale-[0.98]"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">සිංහල</span>
            </button>
          </div>
        </div>
      </div>

      {/* ─── Content ────────────────────────────────────── */}
      <div className="flex-1 overflow-auto px-6 pb-6">
        <div className="max-w-7xl mx-auto">
          {/* Resume Session Banner */}
          {hasSavedSession && (
            <div className="mb-4 px-5 py-4 rounded-xl bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 flex items-center justify-between gap-4 animate-fade-in">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center flex-shrink-0">
                  <RotateCcw className="w-5 h-5 text-amber-600" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-surface-900">Unsaved session found</h4>
                  <p className="text-xs text-surface-500 mt-0.5">
                    You have a {savedLang === 'si' ? 'Sinhala' : 'English'} worksheet from your last session. Resume where you left off?
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={handleDismissSession}
                  className="px-3 py-1.5 text-xs font-medium text-surface-500 hover:text-surface-900 hover:bg-white rounded-lg border border-surface-200 transition-all"
                >
                  Discard
                </button>
                <button
                  onClick={handleResumeSession}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-brand-orange hover:bg-brand-orange-dark rounded-lg shadow-sm transition-all active:scale-[0.98]"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Resume
                </button>
              </div>
            </div>
          )}
          {/* Loading State */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
              <Loader2 className="w-8 h-8 text-brand-orange animate-spin mb-3" />
              <p className="text-sm text-surface-500">Loading worksheets...</p>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-sm text-danger-500 mb-4 animate-fade-in">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Empty State */}
          {!loading && !error && worksheets.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 animate-fade-in">
              <img 
                src="/assets/illustrations/ai_mascot.webp" 
                alt="No Worksheets" 
                className="w-48 h-48 object-contain mb-6 drop-shadow-xl animate-float"
                loading="lazy"
              />
              <h3 className="text-xl font-bold text-surface-900 mb-2">No worksheets yet</h3>
              <p className="text-surface-500 mb-8 text-center max-w-sm leading-relaxed">
                Start your child's learning journey! Create your first worksheet by clicking "Create New" or "සිංහල" above.
              </p>
              <button
                onClick={() => setView('upload')}
                className="flex items-center gap-2 px-6 py-3 bg-brand-orange hover:bg-brand-orange-dark text-white text-sm font-bold rounded-xl shadow-lg shadow-brand-orange/20 hover:shadow-brand-orange/30 transition-all active:scale-[0.98]"
              >
                <Plus className="w-5 h-5" />
                Create Worksheet
              </button>
            </div>
          )}

          {/* My Worksheets */}
          {!loading && myWorksheets.length > 0 && (
            <div className="mb-8">
              <h3 className="text-xs font-semibold text-surface-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                <User className="w-3.5 h-3.5" />
                My Worksheets ({myWorksheets.length})
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {myWorksheets.map((w) => (
                  <WorksheetCard
                    key={w.id}
                    worksheet={w}
                    onView={handleView}
                    onDelete={handleDelete}
                    deletingId={deletingId}
                    viewingId={viewingId}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Others' Worksheets */}
          {!loading && othersWorksheets.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-surface-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                <Eye className="w-3.5 h-3.5" />
                Shared Worksheets ({othersWorksheets.length})
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {othersWorksheets.map((w) => (
                  <WorksheetCard
                    key={w.id}
                    worksheet={w}
                    onView={handleView}
                    onDelete={handleDelete}
                    deletingId={deletingId}
                    viewingId={viewingId}
                    readOnly
                  />
                ))}
              </div>
            </div>
          )}

          {/* No results for search */}
          {!loading && !error && worksheets.length > 0 && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 animate-fade-in">
              <Search className="w-8 h-8 text-surface-300 mb-3" />
              <p className="text-sm text-surface-500">No worksheets match your search.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Worksheet Card Component ──────────────────────────────

function WorksheetCard({ worksheet, onView, onDelete, deletingId, viewingId, readOnly = false }) {
  const w = worksheet;
  const isDeleting = deletingId === w.id;
  const isViewing = viewingId === w.id;

  const dateStr = new Date(w.createdAt).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div
      className={`group bg-white rounded-xl border transition-all duration-200 overflow-hidden ${
        readOnly
          ? 'border-surface-200 hover:border-surface-300'
          : 'border-surface-200 hover:border-brand-orange/30 hover:shadow-md hover:shadow-brand-orange/5'
      }`}
    >
      {/* Card Header */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-semibold text-surface-900 truncate">
              {w.fileName}
            </h4>
            <div className="flex items-center gap-1.5 mt-1">
              <FolderOpen className="w-3 h-3 text-brand-orange flex-shrink-0" />
              <span className="text-[11px] text-surface-500 truncate">
                {w.activityName}
              </span>
            </div>
          </div>

          {/* File type badges */}
          <div className="flex gap-1 flex-shrink-0">
            <span className="px-1.5 py-0.5 bg-blue-50 text-blue-600 text-[9px] font-semibold rounded uppercase">
              HTML
            </span>
            {w.s3PdfKey && (
              <span className="px-1.5 py-0.5 bg-red-50 text-danger-500 text-[9px] font-semibold rounded uppercase">
                PDF
              </span>
            )}
          </div>
        </div>

        {/* Meta info */}
        <div className="flex items-center gap-3 text-[10px] text-surface-400">
          <span className="flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {dateStr}
          </span>
          <span className="flex items-center gap-1">
            <User className="w-3 h-3" />
            {w.ownerEmail.split('@')[0]}
          </span>
        </div>
      </div>

      {/* Card Footer / Actions */}
      <div className="px-4 py-2.5 bg-surface-50/50 border-t border-surface-100 flex items-center justify-between gap-2">
        {readOnly ? (
          <>
            <span className="text-[10px] text-surface-400 flex items-center gap-1">
              <Eye className="w-3 h-3" />
              View only
            </span>
            <button
              onClick={() => onView(w.id)}
              disabled={isViewing}
              className="flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-surface-600 hover:text-brand-orange hover:bg-accent-50 rounded-lg transition-all disabled:opacity-50"
            >
              {isViewing ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Eye className="w-3 h-3" />
              )}
              {isViewing ? 'Loading...' : 'View'}
            </button>
          </>
        ) : (
          <>
            <span className="text-[10px] font-medium text-brand-orange flex items-center gap-1">
              Owner
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => onView(w.id)}
                disabled={isViewing}
                className="flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-surface-600 hover:text-brand-orange hover:bg-accent-50 rounded-lg transition-all disabled:opacity-50"
              >
                {isViewing ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Eye className="w-3 h-3" />
                )}
                {isViewing ? 'Loading...' : 'View'}
              </button>
              <button
                onClick={() => onDelete(w.id, w.fileName)}
                disabled={isDeleting}
                className="flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-surface-500 hover:text-danger-500 hover:bg-red-50 rounded-lg transition-all disabled:opacity-50"
              >
                {isDeleting ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Trash2 className="w-3 h-3" />
                )}
                Delete
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
