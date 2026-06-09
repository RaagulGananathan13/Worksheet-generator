import { useRef, useCallback, useEffect, useMemo, useState } from 'react';
import useWorksheetStore from '../../store/worksheetStore';

/**
 * Canvas v5 — Drag-to-Move, Canvas Panning, Element Editing
 */
export default function Canvas({ containerRef }) {
  const canvasRef = useRef(null);
  const iframeRef = useRef(null);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0 });

  const originalHTML = useWorksheetStore((s) => s.originalHTML);
  const draftHTML = useWorksheetStore((s) => s.draftHTML);
  const reloadCounter = useWorksheetStore((s) => s._reloadCounter);
  const zoom = useWorksheetStore((s) => s.zoom);
  const panOffset = useWorksheetStore((s) => s.panOffset);
  const showGrid = useWorksheetStore((s) => s.showGrid);
  const setZoom = useWorksheetStore((s) => s.setZoom);
  const setPanOffset = useWorksheetStore((s) => s.setPanOffset);
  const setSelectedElement = useWorksheetStore((s) => s.setSelectedElement);
  const setDraftHTML = useWorksheetStore((s) => s.setDraftHTML);

  // Keep ref in sync DURING render (NOT in useEffect which runs AFTER render)
  // This ensures useMemo always reads the current draftHTML on discard/undo/redo
  const draftRef = useRef(draftHTML);
  draftRef.current = draftHTML;

  const editableSrcdoc = useMemo(
    () => buildEditableSrcdoc(draftRef.current || originalHTML),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [originalHTML, reloadCounter]
  );

  // Listen for messages from the iframe
  useEffect(() => {
    function handleMessage(e) {
      if (!e.data || typeof e.data !== 'object') return;
      if (e.data.type === 'ELEMENT_SELECTED') setSelectedElement(e.data.data);
      if (e.data.type === 'ELEMENT_DESELECTED') setSelectedElement(null);
      if (e.data.type === 'HTML_UPDATED') setDraftHTML(e.data.html);
    }
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [setSelectedElement, setDraftHTML]);

  // Zoom with Ctrl+Scroll, Pan with regular scroll
  const zoomRef = useRef(zoom);
  const panRef = useRef(panOffset);
  useEffect(() => { zoomRef.current = zoom; }, [zoom]);
  useEffect(() => { panRef.current = panOffset; }, [panOffset]);

  useEffect(() => {
    const container = containerRef?.current;
    if (!container) return;
    const handleWheel = (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        setZoom(zoomRef.current + (e.deltaY > 0 ? -0.05 : 0.05));
      }
    };
    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => container.removeEventListener('wheel', handleWheel);
  }, [containerRef, setZoom]);

  // Middle-click or Space+drag panning
  useEffect(() => {
    const container = containerRef?.current;
    if (!container) return;

    let spaceDown = false;

    const onKeyDown = (e) => {
      if (e.code === 'Space' && !e.repeat) {
        spaceDown = true;
        container.style.cursor = 'grab';
      }
    };
    const onKeyUp = (e) => {
      if (e.code === 'Space') {
        spaceDown = false;
        container.style.cursor = '';
        setIsPanning(false);
      }
    };
    const onMouseDown = (e) => {
      // Middle click (button 1) or Space+click
      if (e.button === 1 || (spaceDown && e.button === 0)) {
        e.preventDefault();
        setIsPanning(true);
        panStartRef.current = { x: e.clientX - panRef.current.x, y: e.clientY - panRef.current.y };
        container.style.cursor = 'grabbing';
      }
    };
    const onMouseMove = (e) => {
      if (!isPanning && !(e.buttons & 4) && !spaceDown) return;
      // Check if we're actually panning
      if (isPanning || (e.buttons & 4) || (spaceDown && e.buttons & 1)) {
        setPanOffset({
          x: e.clientX - panStartRef.current.x,
          y: e.clientY - panStartRef.current.y,
        });
      }
    };
    const onMouseUp = () => {
      if (isPanning) {
        setIsPanning(false);
        container.style.cursor = spaceDown ? 'grab' : '';
      }
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    container.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      container.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [containerRef, setPanOffset, isPanning]);

  // Click canvas background to deselect
  const handleCanvasClick = useCallback((e) => {
    if (e.target === e.currentTarget || e.target.classList.contains('canvas-background')) {
      iframeRef.current?.contentWindow?.postMessage({ type: 'DESELECT' }, '*');
      setSelectedElement(null);
    }
  }, [setSelectedElement]);

  return (
    <div className="w-full h-full overflow-auto relative bg-surface-100" onClick={handleCanvasClick}>
      {showGrid && (
        <div
          className="canvas-background absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(0,0,0,0.08) 1px, transparent 1px)',
            backgroundSize: `${20 * zoom}px ${20 * zoom}px`,
            backgroundPosition: `${panOffset.x}px ${panOffset.y}px`,
          }}
        />
      )}

      {/* Centering wrapper — flex centers horizontally, padding only for top/bottom */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-start',
          minHeight: '100%',
          paddingTop: 32,
          paddingBottom: 32,
        }}
      >
        <div
          ref={canvasRef}
          style={{
            width: 794,
            minHeight: 1123,
            transform: `scale(${zoom}) translate(${panOffset.x / zoom}px, ${panOffset.y / zoom}px)`,
            transformOrigin: 'top center',
            background: '#fff',
            flexShrink: 0,
            boxShadow: '0 2px 20px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.05)',
            borderRadius: 4,
          }}
        >
          <iframe
            ref={iframeRef}
            key={reloadCounter}
            srcDoc={editableSrcdoc}
            title="Worksheet Editor"
            style={{ width: '100%', minHeight: 1123, border: 'none', display: 'block' }}
            sandbox="allow-same-origin allow-scripts"
          />
        </div>
      </div>
    </div>
  );
}

/* ─── Inject editing + drag-to-move capabilities ─── */
function buildEditableSrcdoc(html) {
  if (!html) return '';

  // Inject Google Fonts so font changes render in the iframe
  const fontsLink = `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Poppins:wght@300;400;500;600;700&family=Roboto:wght@300;400;500;700&family=Open+Sans:wght@300;400;500;600;700&family=Lato:wght@300;400;700&family=Montserrat:wght@300;400;500;600;700&family=Nunito:wght@300;400;500;600;700&family=Raleway:wght@300;400;500;600;700&display=swap">`;

  const editorCSS = `
${fontsLink}
<style id="ws-editor-styles">
[data-ws-id] { transition: outline 0.1s ease; }
[data-ws-id]:hover {
  outline: 1px dashed rgba(245,124,0,0.4) !important;
  cursor: pointer !important;
}
[data-ws-id].ws-selected {
  outline: 2px solid rgba(245,124,0,0.8) !important;
  outline-offset: 2px !important;
  background-color: rgba(245,124,0,0.03) !important;
}
[data-ws-id].ws-dragging {
  opacity: 0.7 !important;
  outline: 2px dashed rgba(245,124,0,0.6) !important;
  cursor: grabbing !important;
  z-index: 9999 !important;
  position: relative !important;
}
[contenteditable]:focus {
  outline: 2px solid rgba(76,175,80,0.7) !important;
  outline-offset: 1px !important;
  background-color: rgba(76,175,80,0.03) !important;
  cursor: text !important;
}
img[data-ws-id]:hover { outline-color: rgba(245,124,0,0.5) !important; }
img[data-ws-id].ws-selected { outline: 2px solid rgba(234,88,12,0.8) !important; }
.ws-empty-visual:hover { outline: 1px dashed rgba(168,85,247,0.4) !important; }
.ws-empty-visual.ws-selected { outline: 2px solid rgba(168,85,247,0.7) !important; }
.ws-drop-indicator {
  outline: 2px solid rgba(16,185,129,0.8) !important;
  outline-offset: -2px !important;
  background-color: rgba(16,185,129,0.05) !important;
}
</style>`;

  const editorScript = `
<script id="ws-editor-script">
(function(){
  var idC=0, selEl=null, dragEl=null, dragStartY=0, dragOffsetY=0;

  function assignIds(el){
    if(!el||!el.tagName)return;
    var t=el.tagName.toLowerCase();
    if(['script','style','link','meta','head','html'].indexOf(t)>=0)return;
    el.setAttribute('data-ws-id','ws-'+(idC++));
    if(el.textContent.trim()==='' && t!=='img' && t!=='input'
       && el.getBoundingClientRect().width>0 && el.getBoundingClientRect().height>0){
      el.classList.add('ws-empty-visual');
    }
    for(var i=0;i<el.children.length;i++) assignIds(el.children[i]);
  }

  function makeEditable(el){
    if(!el||!el.tagName)return;
    var t=el.tagName.toLowerCase();
    if(['script','style','link','meta','img','input','br','hr','iframe'].indexOf(t)>=0)return;
    var hasDT=false;
    for(var n=0;n<el.childNodes.length;n++){
      if(el.childNodes[n].nodeType===3 && el.childNodes[n].textContent.trim().length>0){hasDT=true;break;}
    }
    if((el.children.length===0 && el.textContent.trim().length>0)||hasDT){
      el.contentEditable='true';
    }
    for(var i=0;i<el.children.length;i++) makeEditable(el.children[i]);
  }

  function getDirectText(el){
    var t='';
    for(var n=0;n<el.childNodes.length;n++){
      if(el.childNodes[n].nodeType===3) t+=el.childNodes[n].textContent;
    }
    return t.trim();
  }

  function rgb2hex(rgb){
    if(!rgb||rgb==='transparent'||rgb==='rgba(0, 0, 0, 0)')return 'transparent';
    var m=rgb.match(/\\d+/g);
    if(!m||m.length<3)return rgb;
    return '#'+((1<<24)+(parseInt(m[0])<<16)+(parseInt(m[1])<<8)+parseInt(m[2])).toString(16).slice(1);
  }

  function sendData(el){
    var cs=getComputedStyle(el), r=el.getBoundingClientRect(), t=el.tagName.toLowerCase();
    window.parent.postMessage({type:'ELEMENT_SELECTED',data:{
      wsId:el.getAttribute('data-ws-id'),
      tag:t,
      text:getDirectText(el),
      fullText:el.textContent.trim().substring(0,300),
      classes:Array.from(el.classList).filter(function(c){return c!=='ws-selected'&&c!=='ws-empty-visual'&&c!=='ws-dragging';}),
      imgSrc:t==='img'?el.src:null,
      imgAlt:t==='img'?(el.alt||''):null,
      isInput:t==='input',
      inputType:t==='input'?(el.type||'text'):null,
      isEmptyVisual:el.classList.contains('ws-empty-visual'),
      styles:{
        fontSize:parseFloat(cs.fontSize)||16,
        fontWeight:cs.fontWeight,
        fontFamily:cs.fontFamily,
        color:rgb2hex(cs.color),
        backgroundColor:rgb2hex(cs.backgroundColor),
        textAlign:cs.textAlign,
        display:cs.display,
        width:Math.round(r.width),
        height:Math.round(r.height),
        borderWidth:parseFloat(cs.borderWidth)||0,
        borderColor:rgb2hex(cs.borderColor),
        borderRadius:parseFloat(cs.borderRadius)||0,
        borderStyle:cs.borderStyle,
        opacity:parseFloat(cs.opacity),
        padding:cs.padding,
        margin:cs.margin,
      },
      rect:{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)},
      childCount:el.children.length,
    }},'*');
  }

  function getCleanHTML(){
    var clone=document.documentElement.cloneNode(true);
    var s1=clone.querySelector('#ws-editor-styles');
    var s2=clone.querySelector('#ws-editor-script');
    if(s1)s1.remove(); if(s2)s2.remove();
    clone.querySelectorAll('[data-ws-id]').forEach(function(n){n.removeAttribute('data-ws-id');});
    clone.querySelectorAll('[contenteditable]').forEach(function(n){n.removeAttribute('contenteditable');});
    clone.querySelectorAll('.ws-selected').forEach(function(n){n.classList.remove('ws-selected');});
    clone.querySelectorAll('.ws-empty-visual').forEach(function(n){n.classList.remove('ws-empty-visual');});
    clone.querySelectorAll('.ws-dragging').forEach(function(n){n.classList.remove('ws-dragging');});
    clone.querySelectorAll('.ws-drop-indicator').forEach(function(n){n.classList.remove('ws-drop-indicator');});
    return '<!DOCTYPE html>\\n'+clone.outerHTML;
  }

  assignIds(document.body);
  makeEditable(document.body);

  /* ── Interaction: click=select, dblclick=edit, drag=move ── */
  var isEditing=false;

  /* Double-click to enter text editing mode */
  document.addEventListener('dblclick',function(e){
    var el=e.target;
    if(!el.hasAttribute('data-ws-id')) el=el.closest('[data-ws-id]');
    if(!el) return;

    // Select it
    if(selEl && selEl!==el) selEl.classList.remove('ws-selected');
    selEl=el;
    el.classList.add('ws-selected');
    sendData(el);

    // Focus for editing
    if(el.getAttribute('contenteditable')==='true'){
      isEditing=true;
      el.focus();
    } else {
      var ce=el.querySelector('[contenteditable="true"]');
      if(ce){ isEditing=true; ce.focus(); }
    }
  },true);

  /* Mousedown: start drag or click-to-select */
  document.addEventListener('mousedown',function(e){
    // Don't interfere with text editing
    if(isEditing && document.activeElement && document.activeElement.getAttribute('contenteditable')==='true'){
      return;
    }

    var el=e.target;
    if(!el.hasAttribute('data-ws-id')) el=el.closest('[data-ws-id]');
    if(!el) return;

    var startX=e.clientX, startY=e.clientY;
    var moved=false;
    var dragStartLeft=parseFloat(el.style.left)||0;
    var dragStartTop=parseFloat(el.style.top)||0;

    function onMove(ev){
      var dx=ev.clientX-startX, dy=ev.clientY-startY;
      if(Math.abs(dx)>5 || Math.abs(dy)>5){
        if(!moved){
          moved=true;
          isEditing=false;
          dragEl=el;
          el.classList.add('ws-dragging');
          // Select on drag start
          if(selEl && selEl!==el) selEl.classList.remove('ws-selected');
          selEl=el;
          el.classList.add('ws-selected');
        }
        el.style.position='relative';
        el.style.left=(dragStartLeft+dx)+'px';
        el.style.top=(dragStartTop+dy)+'px';
      }
    }

    function onUp(ev){
      document.removeEventListener('mousemove',onMove);
      document.removeEventListener('mouseup',onUp);

      if(moved && dragEl){
        // Finished drag
        dragEl.classList.remove('ws-dragging');
        dragEl=null;
        sendData(el);
        window.parent.postMessage({type:'HTML_UPDATED',html:getCleanHTML()},'*');
      } else {
        // Was a click (no drag) — select element
        isEditing=false;
        if(selEl && selEl!==el) selEl.classList.remove('ws-selected');
        selEl=el;
        el.classList.add('ws-selected');
        sendData(el);
      }
    }

    document.addEventListener('mousemove',onMove);
    document.addEventListener('mouseup',onUp);
  });

  /* Content editing */
  document.body.addEventListener('input',function(e){
    var el=e.target;
    if(el.hasAttribute('data-ws-id')&&selEl===el) sendData(el);
    window.parent.postMessage({type:'HTML_UPDATED',html:getCleanHTML()},'*');
  });

  /* Exit editing mode when clicking outside */
  document.addEventListener('focusout',function(){
    isEditing=false;
  });

  /* Commands from parent */
  window.addEventListener('message',function(e){
    if(!e.data||typeof e.data!=='object')return;

    if(e.data.type==='UPDATE_ELEMENT'){
      var el=document.querySelector('[data-ws-id="'+e.data.wsId+'"]');
      if(!el)return;
      var p=e.data.property, v=e.data.value;

      if(p==='text'){
        for(var n=0;n<el.childNodes.length;n++){
          if(el.childNodes[n].nodeType===3&&el.childNodes[n].textContent.trim().length>0){
            el.childNodes[n].textContent=v; break;
          }
        }
        if(el.children.length===0) el.textContent=v;
      }
      else if(p==='imgSrc'&&el.tagName==='IMG'){el.src=v;}
      else if(p==='imgAlt'&&el.tagName==='IMG'){el.alt=v;}
      else if(p==='fontSize'){el.style.fontSize=v+'px';}
      else if(p==='fontWeight'){el.style.fontWeight=v;}
      else if(p==='fontFamily'){el.style.fontFamily=v;}
      else if(p==='color'){el.style.color=v;}
      else if(p==='backgroundColor'){el.style.backgroundColor=v;}
      else if(p==='textAlign'){el.style.textAlign=v;}
      else if(p==='borderWidth'){el.style.borderWidth=v+'px';}
      else if(p==='borderColor'){el.style.borderColor=v;}
      else if(p==='borderRadius'){el.style.borderRadius=v+'px';}
      else if(p==='borderStyle'){el.style.borderStyle=v;}
      else if(p==='opacity'){el.style.opacity=v;}
      else if(p==='padding'){el.style.padding=v;}
      else if(p==='margin'){el.style.margin=v;}
      else if(p==='width'){el.style.width=Math.max(1,v)+'px';}
      else if(p==='height'){el.style.height=Math.max(1,v)+'px';}
      else if(p==='display'){el.style.display=v;}

      sendData(el);
      window.parent.postMessage({type:'HTML_UPDATED',html:getCleanHTML()},'*');
    }

    if(e.data.type==='DESELECT'){
      if(selEl){selEl.classList.remove('ws-selected');selEl=null;}
      isEditing=false;
      window.parent.postMessage({type:'ELEMENT_DESELECTED'},'*');
    }

    if(e.data.type==='DELETE_ELEMENT'){
      var el=document.querySelector('[data-ws-id="'+e.data.wsId+'"]');
      if(el){el.remove();selEl=null;}
      window.parent.postMessage({type:'ELEMENT_DESELECTED'},'*');
      window.parent.postMessage({type:'HTML_UPDATED',html:getCleanHTML()},'*');
    }

    if(e.data.type==='DUPLICATE_ELEMENT'){
      var el=document.querySelector('[data-ws-id="'+e.data.wsId+'"]');
      if(el){
        var clone=el.cloneNode(true);
        /* Reassign IDs to clone AND all children to prevent ID conflicts */
        clone.setAttribute('data-ws-id','ws-'+(idC++));
        clone.querySelectorAll('[data-ws-id]').forEach(function(child){
          child.setAttribute('data-ws-id','ws-'+(idC++));
        });
        el.parentNode.insertBefore(clone,el.nextSibling);
        makeEditable(clone);
        /* Auto-select the clone */
        if(selEl) selEl.classList.remove('ws-selected');
        selEl=clone;
        clone.classList.add('ws-selected');
        sendData(clone);
      }
      window.parent.postMessage({type:'HTML_UPDATED',html:getCleanHTML()},'*');
    }

    if(e.data.type==='TOGGLE_VISIBILITY'){
      var el=document.querySelector('[data-ws-id="'+e.data.wsId+'"]');
      if(el){
        el.style.display=el.style.display==='none'?'':'none';
        sendData(el);
        window.parent.postMessage({type:'HTML_UPDATED',html:getCleanHTML()},'*');
      }
    }
  });
})();
` + `</` + `script>`;


  if (html.includes('</body>')) {
    return html.replace('</body>', editorCSS + editorScript + '\n</body>');
  }
  return html + editorCSS + editorScript;
}
