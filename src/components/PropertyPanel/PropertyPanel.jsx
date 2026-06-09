import { useState, useEffect, useRef } from 'react';
import {
  Type, Image, Move, Palette, Layers, MousePointer,
  AlignLeft, AlignCenter, AlignRight,
  Trash2, Copy, Eye, EyeOff, Box, Maximize2,
} from 'lucide-react';
import useWorksheetStore from '../../store/worksheetStore';

/* ─── Font families available ─── */
const FONT_FAMILIES = [
  { label: 'Inter', value: "'Inter', sans-serif", match: 'inter' },
  { label: 'Poppins', value: "'Poppins', sans-serif", match: 'poppins' },
  { label: 'Roboto', value: "'Roboto', sans-serif", match: 'roboto' },
  { label: 'Open Sans', value: "'Open Sans', sans-serif", match: 'open sans' },
  { label: 'Lato', value: "'Lato', sans-serif", match: 'lato' },
  { label: 'Montserrat', value: "'Montserrat', sans-serif", match: 'montserrat' },
  { label: 'Nunito', value: "'Nunito', sans-serif", match: 'nunito' },
  { label: 'Raleway', value: "'Raleway', sans-serif", match: 'raleway' },
  { label: 'Georgia', value: "Georgia, serif", match: 'georgia' },
  { label: 'Times New Roman', value: "'Times New Roman', serif", match: 'times new roman' },
  { label: 'Courier New', value: "'Courier New', monospace", match: 'courier new' },
  { label: 'Arial', value: "Arial, sans-serif", match: 'arial' },
  { label: 'Verdana', value: "Verdana, sans-serif", match: 'verdana' },
  { label: 'Comic Sans', value: "'Comic Sans MS', cursive", match: 'comic sans' },
];

/**
 * Match a computed fontFamily string (e.g. "Poppins, sans-serif")
 * to the closest option value in FONT_FAMILIES.
 */
function matchFontFamily(computed) {
  if (!computed) return FONT_FAMILIES[0].value;
  const lower = computed.toLowerCase().replace(/["']/g, '');
  for (const f of FONT_FAMILIES) {
    if (lower.includes(f.match)) return f.value;
  }
  return FONT_FAMILIES[0].value; // fallback to Inter
}

/* ─── Send command to iframe ─── */
function sendToIframe(type, payload) {
  const iframe = document.querySelector('iframe[title="Worksheet Editor"]');
  if (iframe?.contentWindow) {
    iframe.contentWindow.postMessage({ type, ...payload }, '*');
  }
}
function updateElement(wsId, property, value) {
  sendToIframe('UPDATE_ELEMENT', { wsId, property, value });
}

/* ─── Reusable Input Components ─── */

function LiveNumInput({ label, value, onChange, min, max, step = 1, unit = 'px' }) {
  const [local, setLocal] = useState(String(Math.round(value ?? 0)));
  const [focused, setFocused] = useState(false);
  const timerRef = useRef(null);

  // Sync from store when not focused
  useEffect(() => {
    if (!focused) setLocal(String(Math.round(value ?? 0)));
  }, [value, focused]);

  const commit = (val) => {
    const num = parseFloat(val);
    if (!isNaN(num)) onChange(num);
  };

  const debouncedCommit = (val) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => commit(val), 300);
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-surface-500 w-16 shrink-0 font-medium">{label}</span>
      <input type="number" value={local} min={min} max={max} step={step}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); clearTimeout(timerRef.current); commit(local); }}
        onKeyDown={(e) => { if (e.key === 'Enter') { clearTimeout(timerRef.current); commit(local); e.target.blur(); } }}
        onChange={(e) => { setLocal(e.target.value); debouncedCommit(e.target.value); }}
        className="flex-1 bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800
                   focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/20 outline-none
                   [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" />
      {unit && <span className="text-[10px] text-surface-400 w-5">{unit}</span>}
    </div>
  );
}

function LiveTxtInput({ label, value, onChange, placeholder, mono }) {
  const [local, setLocal] = useState(value || '');
  const [focused, setFocused] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!focused) setLocal(value || '');
  }, [value, focused]);

  const debouncedCommit = (val) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onChange(val), 400);
  };

  return (
    <div className="space-y-1">
      <label className="text-[11px] text-surface-500 font-medium">{label}</label>
      <input type="text" value={local} placeholder={placeholder}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); clearTimeout(timerRef.current); onChange(local); }}
        onKeyDown={(e) => { if (e.key === 'Enter') { clearTimeout(timerRef.current); onChange(local); e.target.blur(); } }}
        onChange={(e) => { setLocal(e.target.value); debouncedCommit(e.target.value); }}
        className={`w-full bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800
                   focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/20 outline-none placeholder:text-surface-400 ${mono ? 'font-mono' : ''}`} />
    </div>
  );
}

function LiveTxtArea({ label, value, onChange, rows = 2 }) {
  const [local, setLocal] = useState(value || '');
  const [focused, setFocused] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!focused) setLocal(value || '');
  }, [value, focused]);

  const debouncedCommit = (val) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onChange(val), 400);
  };

  return (
    <div className="space-y-1">
      <label className="text-[11px] text-surface-500 font-medium">{label}</label>
      <textarea value={local} rows={rows}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); clearTimeout(timerRef.current); onChange(local); }}
        onChange={(e) => { setLocal(e.target.value); debouncedCommit(e.target.value); }}
        className="w-full bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800
                   focus:border-brand-orange focus:ring-1 focus:ring-brand-orange/20 outline-none resize-y leading-relaxed" />
    </div>
  );
}

function LiveClrInput({ label, value, onChange }) {
  const hex = (!value || value === 'transparent') ? '#000000' : value;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-surface-500 w-16 shrink-0 font-medium">{label}</span>
      <div className="relative">
        <input type="color" value={hex}
          onChange={(e) => onChange(e.target.value)}
          className="w-8 h-8 rounded-lg border-2 border-surface-200 cursor-pointer bg-transparent p-0 shrink-0" />
      </div>
      <input type="text" value={value || ''} readOnly
        className="flex-1 bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800 font-mono outline-none" />
    </div>
  );
}

/* ─── Section wrapper with collapsible toggle ─── */
function Sec({ icon: Icon, title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-surface-100">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-2.5 w-full hover:bg-surface-50 transition-colors">
        <Icon className="w-3.5 h-3.5 text-brand-orange" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-surface-700 flex-1 text-left">{title}</span>
        <svg className={`w-3 h-3 text-surface-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="px-4 pb-4 pt-1 space-y-3 animate-fade-in">{children}</div>}
    </div>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between text-[11px] py-1.5 px-3 bg-surface-50 rounded-lg">
      <span className="text-surface-500">{label}</span>
      <span className="text-surface-700 font-mono truncate ml-2 max-w-[130px]">{String(value)}</span>
    </div>
  );
}

function getLabel(el) {
  if (el.tag === 'img') return 'Image';
  if (['h1','h2','h3','h4','h5','h6'].includes(el.tag)) return `Heading (${el.tag})`;
  if (el.tag === 'span') return 'Text Span';
  if (el.tag === 'p') return 'Paragraph';
  if (el.tag === 'input') return `Input (${el.inputType || 'text'})`;
  if (el.isEmptyVisual) return 'Visual Element';
  if (el.tag === 'div' && el.childCount === 0) return 'Empty Box';
  if (el.tag === 'div') return 'Container';
  if (el.tag === 'td') return 'Table Cell';
  if (el.tag === 'th') return 'Table Header';
  if (el.tag === 'tr') return 'Table Row';
  if (el.tag === 'table') return 'Table';
  if (el.tag === 'li') return 'List Item';
  if (el.tag === 'ul' || el.tag === 'ol') return 'List';
  if (el.tag === 'a') return 'Link';
  if (el.tag === 'strong' || el.tag === 'b') return 'Bold Text';
  if (el.tag === 'em' || el.tag === 'i') return 'Italic Text';
  return el.tag.toUpperCase();
}

/* ─── MAIN ─── */
export default function PropertyPanel() {
  const el = useWorksheetStore((s) => s.selectedElement);
  const meta = useWorksheetStore((s) => s.worksheetMeta);
  const blocks = useWorksheetStore((s) => s.blocks);

  if (!el) {
    return (
      <div className="w-full h-full border-l border-surface-200 bg-white flex flex-col">
        <div className="p-4 border-b border-surface-100">
          <h3 className="text-sm font-semibold text-surface-900">Properties</h3>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-6">
          <div className="w-16 h-16 rounded-2xl bg-accent-50 flex items-center justify-center">
            <MousePointer className="w-7 h-7 text-brand-orange" />
          </div>
          <p className="text-sm text-surface-800 font-medium">Click any element</p>
          <p className="text-[11px] text-surface-500 mt-1 leading-relaxed">
            Click on any text, image, or box<br />to select and edit it.
          </p>
          <div className="mt-4 w-full space-y-1.5">
            <InfoRow label="Worksheet" value={meta.title} />
            <InfoRow label="Elements" value={`${blocks.length} detected`} />
            <InfoRow label="Page" value={`${meta.width} × ${meta.height}`} />
          </div>
          <div className="mt-3 bg-accent-50 rounded-lg p-3 text-[11px] text-surface-600 leading-relaxed text-left w-full">
            <strong className="text-brand-orange">Shortcuts:</strong><br />
            • Ctrl+S — Save changes<br />
            • Ctrl+Z / Ctrl+Shift+Z — Undo / Redo<br />
            • Ctrl+E — Export<br />
            • Ctrl+scroll — Zoom<br />
            • Ctrl+0 — Reset zoom
          </div>
        </div>
      </div>
    );
  }

  const isImg = el.tag === 'img';
  const isText = !isImg && !el.isInput && (el.text.length > 0 || el.fullText.length > 0);
  const s = el.styles;

  // Normalize fontFamily for the dropdown — match computed style to option value
  const matchedFont = matchFontFamily(s.fontFamily);

  return (
    <div className="w-full h-full border-l border-surface-200 bg-white flex flex-col overflow-y-auto">
      {/* Header */}
      <div className="p-4 border-b border-surface-100 shrink-0">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${
            isImg ? 'bg-orange-100' : el.isEmptyVisual ? 'bg-purple-100' : 'bg-accent-50'
          }`}>
            {isImg ? <Image className="w-4 h-4 text-brand-orange" /> :
             el.isEmptyVisual ? <Box className="w-4 h-4 text-purple-600" /> :
             <Type className="w-4 h-4 text-brand-orange" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-surface-900">{getLabel(el)}</p>
            <p className="text-[10px] text-surface-400 font-mono truncate">
              &lt;{el.tag}{el.classes.length > 0 ? ` .${el.classes[0]}` : ''}&gt;
            </p>
          </div>
        </div>
        {/* Quick actions */}
        <div className="flex gap-1.5 mt-3">
          <button onClick={() => sendToIframe('DUPLICATE_ELEMENT', { wsId: el.wsId })}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-surface-50 hover:bg-surface-100 text-surface-600 hover:text-surface-900 text-[11px] transition-colors border border-surface-200">
            <Copy className="w-3 h-3" /> Duplicate
          </button>
          <button onClick={() => sendToIframe('TOGGLE_VISIBILITY', { wsId: el.wsId })}
            className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-surface-50 hover:bg-surface-100 text-surface-600 hover:text-surface-900 text-[11px] transition-colors border border-surface-200">
            {s.display === 'none' ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            {s.display === 'none' ? 'Show' : 'Hide'}
          </button>
          <button onClick={() => sendToIframe('DELETE_ELEMENT', { wsId: el.wsId })}
            className="flex items-center justify-center gap-1 py-2 px-3 rounded-lg bg-red-50 hover:bg-red-100 text-danger-500 text-[11px] transition-colors border border-red-200">
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* ── Content ── */}
      {isText && (
        <Sec icon={Type} title="Content">
          <LiveTxtArea label="Text" value={el.text} onChange={(v) => updateElement(el.wsId, 'text', v)} rows={2} />
        </Sec>
      )}
      {isImg && (
        <Sec icon={Image} title="Image">
          <LiveTxtInput label="Image URL" value={el.imgSrc} onChange={(v) => updateElement(el.wsId, 'imgSrc', v)}
            placeholder="https://..." mono />
          <LiveTxtInput label="Alt Text" value={el.imgAlt} onChange={(v) => updateElement(el.wsId, 'imgAlt', v)}
            placeholder="Description" />
          {el.imgSrc && (
            <div className="rounded-lg overflow-hidden border border-surface-200 bg-surface-50">
              <img src={el.imgSrc} alt="" className="w-full h-20 object-contain"
                onError={(e) => { e.target.style.display = 'none'; }} />
            </div>
          )}
        </Sec>
      )}

      {/* ── Typography ── */}
      {!isImg && (
        <Sec icon={Type} title="Typography">
          {/* Font Family — uses normalized matching */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-surface-500 w-16 shrink-0 font-medium">Font</span>
            <select value={matchedFont}
              onChange={(e) => updateElement(el.wsId, 'fontFamily', e.target.value)}
              className="flex-1 bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800
                         focus:border-brand-orange outline-none cursor-pointer"
              style={{ fontFamily: matchedFont }}>
              {FONT_FAMILIES.map(f => (
                <option key={f.label} value={f.value} style={{ fontFamily: f.value }}>{f.label}</option>
              ))}
            </select>
          </div>

          <LiveNumInput label="Size" value={s.fontSize} onChange={(v) => updateElement(el.wsId, 'fontSize', v)}
            min={6} max={120} />

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-surface-500 w-16 shrink-0 font-medium">Weight</span>
            <select value={s.fontWeight || '400'}
              onChange={(e) => updateElement(el.wsId, 'fontWeight', e.target.value)}
              className="flex-1 bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800
                         focus:border-brand-orange outline-none cursor-pointer">
              <option value="300">Light (300)</option>
              <option value="400">Regular (400)</option>
              <option value="500">Medium (500)</option>
              <option value="600">Semibold (600)</option>
              <option value="700">Bold (700)</option>
              <option value="800">Extra Bold (800)</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-surface-500 w-16 shrink-0 font-medium">Align</span>
            <div className="flex gap-1">
              {[{ v: 'left', I: AlignLeft }, { v: 'center', I: AlignCenter }, { v: 'right', I: AlignRight }].map(({ v, I }) => (
                <button key={v} onClick={() => updateElement(el.wsId, 'textAlign', v)}
                  className={`p-2 rounded-lg transition-colors ${s.textAlign === v
                    ? 'bg-accent-50 text-brand-orange border border-brand-orange/30'
                    : 'bg-surface-50 text-surface-500 hover:text-surface-800 border border-surface-200'}`}>
                  <I className="w-3.5 h-3.5" />
                </button>
              ))}
            </div>
          </div>
        </Sec>
      )}

      {/* ── Colors — Live update via onChange ── */}
      <Sec icon={Palette} title="Colors">
        {!isImg && <LiveClrInput label="Text" value={s.color} onChange={(v) => updateElement(el.wsId, 'color', v)} />}
        <LiveClrInput label="Fill" value={s.backgroundColor} onChange={(v) => updateElement(el.wsId, 'backgroundColor', v)} />
        <LiveNumInput label="Opacity" value={Math.round((s.opacity ?? 1) * 100)} min={0} max={100} unit="%"
          onChange={(v) => updateElement(el.wsId, 'opacity', v / 100)} />
      </Sec>

      {/* ── Border ── */}
      <Sec icon={Box} title="Border" defaultOpen={false}>
        <LiveNumInput label="Width" value={s.borderWidth} onChange={(v) => updateElement(el.wsId, 'borderWidth', v)} min={0} max={20} />
        <LiveClrInput label="Color" value={s.borderColor} onChange={(v) => updateElement(el.wsId, 'borderColor', v)} />
        <LiveNumInput label="Radius" value={s.borderRadius} onChange={(v) => updateElement(el.wsId, 'borderRadius', v)} min={0} max={100} />
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-surface-500 w-16 shrink-0 font-medium">Style</span>
          <select value={s.borderStyle || 'none'}
            onChange={(e) => updateElement(el.wsId, 'borderStyle', e.target.value)}
            className="flex-1 bg-surface-50 border border-surface-200 rounded-lg px-3 py-2 text-xs text-surface-800
                       focus:border-brand-orange outline-none cursor-pointer">
            <option value="none">None</option>
            <option value="solid">Solid</option>
            <option value="dashed">Dashed</option>
            <option value="dotted">Dotted</option>
            <option value="double">Double</option>
          </select>
        </div>
      </Sec>

      {/* ── Spacing ── */}
      <Sec icon={Maximize2} title="Spacing" defaultOpen={false}>
        <LiveTxtInput label="Padding" value={s.padding} onChange={(v) => updateElement(el.wsId, 'padding', v)}
          placeholder="e.g. 10px 20px" mono />
        <LiveTxtInput label="Margin" value={s.margin} onChange={(v) => updateElement(el.wsId, 'margin', v)}
          placeholder="e.g. 0 auto" mono />
      </Sec>

      {/* ── Dimensions ── */}
      <Sec icon={Move} title="Size" defaultOpen={false}>
        <div className="grid grid-cols-2 gap-3">
          <LiveNumInput label="W" value={s.width} onChange={(v) => updateElement(el.wsId, 'width', v)} min={0} />
          <LiveNumInput label="H" value={s.height} onChange={(v) => updateElement(el.wsId, 'height', v)} min={0} />
        </div>
      </Sec>

      {/* ── Info ── */}
      <Sec icon={Layers} title="Info" defaultOpen={false}>
        <InfoRow label="Tag" value={`<${el.tag}>`} />
        <InfoRow label="ID" value={el.wsId} />
        {el.classes.length > 0 && <InfoRow label="Classes" value={el.classes.join(', ')} />}
        <InfoRow label="Display" value={s.display} />
        <InfoRow label="Font" value={FONT_FAMILIES.find(f => f.value === matchedFont)?.label || 'Unknown'} />
      </Sec>
    </div>
  );
}
