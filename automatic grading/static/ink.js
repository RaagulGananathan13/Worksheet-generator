// Ink coordinates and stroke width are relative to the answer region. Resizing,
// zooming and changing tablet orientation never changes the stored handwriting.
export function drawStrokes(context, strokes, width, height, color = '#172b4d') {
  context.clearRect(0, 0, width, height);
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  for (const stroke of strokes || []) {
    const points = stroke.points || [];
    if (!points.length) continue;
    const base = Math.max(0.8, (stroke.width || 0.008) * width);
    if (points.length === 1) {
      context.beginPath();
      context.arc(points[0].x * width, points[0].y * height, base * (0.4 + 0.6 * points[0].p) / 2, 0, Math.PI * 2);
      context.fill();
    }
    for (let i = 1; i < points.length; i += 1) {
      const previous = points[i - 1];
      const point = points[i];
      context.lineWidth = base * (0.4 + 0.6 * ((previous.p + point.p) / 2));
      context.beginPath();
      context.moveTo(previous.x * width, previous.y * height);
      context.lineTo(point.x * width, point.y * height);
      context.stroke();
    }
  }
}

const copy = (value) => JSON.parse(JSON.stringify(value));
const clamp = (value) => Math.max(0, Math.min(1, value));

export class InkCanvas {
  constructor(canvas, { strokes = [], onChange, onStart, onLimit, selectOnTap, readOnly = false, finger = false, tool = 'pen', width = 0.008, historyLimit = 40 } = {}) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d');
    this.strokes = copy(strokes);
    this.onChange = onChange;
    this.onStart = onStart;
    this.onLimit = onLimit;
    this.selectOnTap = selectOnTap;
    this.readOnly = readOnly;
    this.finger = finger;
    this.tool = tool;
    this.width = width;
    this.undoStack = [];
    this.historyLimit = historyLimit;
    this.activePointer = null;
    this.abort = new AbortController();
    const options = { signal: this.abort.signal };
    canvas.addEventListener('pointerdown', (event) => this.start(event), options);
    canvas.addEventListener('pointermove', (event) => this.move(event), options);
    canvas.addEventListener('pointerup', (event) => this.finish(event), options);
    canvas.addEventListener('pointercancel', (event) => this.finish(event), options);
    canvas.addEventListener('lostpointercapture', (event) => this.finish(event), options);
    canvas.addEventListener('pointerenter', (event) => {
      if (!this.readOnly && event.pointerType === 'pen') canvas.style.touchAction = 'none';
      else this.setTouchAction();
    }, options);
    canvas.addEventListener('pointerleave', () => { if (this.activePointer === null) this.setTouchAction(); }, options);
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
    this.setTouchAction();
    this.resize();
  }

  setTouchAction() {
    this.canvas.style.touchAction = !this.readOnly && this.finger ? 'none' : 'pan-y pinch-zoom';
    this.canvas.style.cursor = this.readOnly ? 'default' : this.tool === 'eraser' ? 'cell' : 'crosshair';
  }

  configure({ finger = this.finger, tool = this.tool, width = this.width, readOnly = this.readOnly } = {}) {
    Object.assign(this, { finger, tool, width, readOnly });
    this.setTouchAction();
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 3);
    this.canvas.width = Math.round(rect.width * ratio);
    this.canvas.height = Math.round(rect.height * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.drawWidth = rect.width;
    this.drawHeight = rect.height;
    this.render();
  }

  point(event) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height), p: clamp(event.pointerType === 'pen' && event.pressure > 0 ? event.pressure : 0.5) };
  }

  start(event) {
    if (this.readOnly || this.activePointer !== null || (event.pointerType === 'touch' && !this.finger)) return;
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    if (this.tool !== 'eraser' && event.button !== 5 && event.buttons !== 32 && this.strokes.length >= 200) {
      this.onLimit?.('This answer has reached 200 strokes. Erase unnecessary strokes before continuing.');
      return;
    }
    event.preventDefault();
    this.activePointer = event.pointerId;
    this.canvas.style.touchAction = 'none';
    this.canvas.setPointerCapture(event.pointerId);
    // Decide before onStart selects the field. A stationary first contact on a
    // worksheet field selects it; a drag still captures its complete first stroke.
    this.selectionGesture = Boolean(this.selectOnTap?.());
    this.startPosition = { x: event.clientX, y: event.clientY };
    this.gestureMoved = false;
    this.onStart?.();
    this.remember();
    this.erasing = this.tool === 'eraser' || event.button === 5 || event.buttons === 32;
    if (this.erasing) this.erase(this.point(event));
    else {
      this.currentStroke = { points: [this.point(event)], width: this.width };
      this.strokes.push(this.currentStroke);
    }
    this.render();
  }

  move(event) {
    if (this.activePointer !== event.pointerId) return;
    event.preventDefault();
    const events = typeof event.getCoalescedEvents === 'function' ? event.getCoalescedEvents() : [];
    for (const sample of events.length ? events : [event]) {
      if (Math.hypot(sample.clientX - this.startPosition.x, sample.clientY - this.startPosition.y) > 3) this.gestureMoved = true;
      const point = this.point(sample);
      if (this.erasing) this.erase(point);
      else if (this.currentStroke) {
        if (this.currentStroke.points.length >= 3999) this.currentStroke.points = this.currentStroke.points.filter((_point, index, points) => index % 2 === 0 || index === points.length - 1);
        const previous = this.currentStroke.points.at(-1);
        if (Math.hypot(point.x - previous.x, point.y - previous.y) > 0.0004) this.currentStroke.points.push(point);
      }
    }
    this.render();
  }

  finish(event) {
    if (this.activePointer !== event.pointerId) return;
    if (event.type === 'pointerup') this.move(event);
    const discardContact = !this.erasing && !this.gestureMoved && (this.selectionGesture || event.type !== 'pointerup');
    if (discardContact) {
      this.strokes = this.strokes.filter((stroke) => stroke !== this.currentStroke);
      if (this.historyLimit) this.undoStack.pop();
    }
    const pointer = this.activePointer;
    this.activePointer = null;
    this.currentStroke = null;
    if (this.canvas.hasPointerCapture(pointer)) this.canvas.releasePointerCapture(pointer);
    this.setTouchAction();
    if (discardContact) { this.render(); return; }
    const total = this.strokes.reduce((sum, stroke) => sum + stroke.points.length, 0);
    if (total > 20000) {
      const ratio = 18000 / total;
      this.strokes.forEach((stroke) => {
        const target = Math.max(2, Math.floor(stroke.points.length * ratio));
        if (stroke.points.length > target) stroke.points = Array.from({ length: target }, (_value, index) => stroke.points[Math.round(index * (stroke.points.length - 1) / (target - 1))]);
      });
      this.render();
    }
    this.changed();
  }

  erase(point) {
    const aspect = (this.drawHeight || 1) / (this.drawWidth || 1);
    const radius = Math.max(0.018, 12 / (this.drawWidth || 300));
    const distance = (p) => Math.hypot(point.x - p.x, (point.y - p.y) * aspect);
    this.strokes = this.strokes.filter((stroke) => !stroke.points.some((p, index) => {
      if (distance(p) <= radius) return true;
      if (!index) return false;
      const before = stroke.points[index - 1];
      const dx = p.x - before.x;
      const dy = (p.y - before.y) * aspect;
      const length = dx * dx + dy * dy;
      if (!length) return false;
      const t = clamp(((point.x - before.x) * dx + (point.y - before.y) * aspect * dy) / length);
      return Math.hypot(point.x - before.x - t * dx, (point.y - before.y) * aspect - t * dy) <= radius;
    }));
  }

  remember() {
    if (!this.historyLimit) return;
    this.undoStack.push(copy(this.strokes));
    if (this.undoStack.length > this.historyLimit) this.undoStack.shift();
  }

  undo() {
    if (this.readOnly || !this.undoStack.length) return;
    this.strokes = this.undoStack.pop();
    this.render();
    this.changed();
  }

  clear() {
    if (this.readOnly || !this.strokes.length) return;
    this.remember();
    this.strokes = [];
    this.render();
    this.changed();
  }

  setStrokes(strokes, { resetHistory = false } = {}) {
    if (this.activePointer !== null) return;
    this.strokes = copy(strokes || []);
    if (resetHistory) this.undoStack = [];
    this.render();
  }

  changed() { this.onChange?.(copy(this.strokes), this); }
  render() {
    const visible = this.selectionGesture && !this.gestureMoved && this.currentStroke
      ? this.strokes.filter((stroke) => stroke !== this.currentStroke) : this.strokes;
    drawStrokes(this.context, visible, this.drawWidth || 1, this.drawHeight || 1);
  }
  destroy() { this.observer.disconnect(); this.abort.abort(); }
}
