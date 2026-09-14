import test from 'node:test';
import assert from 'node:assert/strict';
import { InkCanvas } from '../static/ink.js';

// Exercise the actual dependency-free browser ink module with only the drawing
// surface mocked. No browser, npm package, network or model download is needed.
globalThis.window = { devicePixelRatio: 2 };
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};

function surface() {
  return {
    style: {}, width: 0, height: 0, capture: null, handlers: {},
    rect: { left: 0, top: 0, width: 400, height: 200 },
    getContext() {
      return { clearRect() {}, setTransform() {}, beginPath() {}, arc() {}, fill() {}, moveTo() {}, lineTo() {}, stroke() {} };
    },
    addEventListener(name, handler) { this.handlers[name] = handler; },
    getBoundingClientRect() { return this.rect; },
    setPointerCapture(id) { this.capture = id; },
    hasPointerCapture(id) { return this.capture === id; },
    releasePointerCapture() { this.capture = null; },
  };
}

function pointer(x, y, options = {}) {
  return {
    pointerType: 'pen', pointerId: 1, button: 0, buttons: 1,
    pressure: 0.6, clientX: x, clientY: y, preventDefault() {}, ...options,
  };
}

function write(ink, points = [[20, 20], [100, 120], [180, 160]]) {
  ink.start(pointer(...points[0]));
  for (const point of points.slice(1, -1)) ink.move(pointer(...point));
  ink.finish(pointer(...points.at(-1), { type: 'pointerup' }));
}

test('pen stores page-independent coordinates, width and pressure once per completed stroke', () => {
  let changes = 0;
  const canvas = surface();
  const ink = new InkCanvas(canvas, { width: 0.009, onChange: () => { changes += 1; } });
  write(ink);
  assert.equal(ink.strokes.length, 1);
  assert.deepEqual(ink.strokes[0].points[0], { x: 0.05, y: 0.1, p: 0.6 });
  assert.deepEqual(ink.strokes[0].points.at(-1), { x: 0.45, y: 0.8, p: 0.6 });
  assert.equal(ink.strokes[0].width, 0.009);
  assert.equal(changes, 1);
  assert.equal(canvas.capture, null);
  ink.destroy();
});

test('tablet orientation and high-DPI redraw preserve saved geometry', () => {
  const canvas = surface();
  const ink = new InkCanvas(canvas);
  write(ink);
  const original = JSON.stringify(ink.strokes);
  canvas.rect = { left: 10, top: 20, width: 800, height: 400 };
  ink.resize();
  assert.equal(canvas.width, 1600);
  assert.equal(canvas.height, 800);
  assert.equal(JSON.stringify(ink.strokes), original);
  ink.destroy();
});

test('finger input scrolls by default and writes only when explicitly enabled', () => {
  const ink = new InkCanvas(surface());
  ink.start(pointer(50, 50, { pointerType: 'touch' }));
  assert.equal(ink.activePointer, null);
  assert.equal(ink.strokes.length, 0);
  ink.configure({ finger: true });
  ink.start(pointer(50, 50, { pointerType: 'touch' }));
  ink.finish(pointer(50, 50, { pointerType: 'touch', type: 'pointerup' }));
  assert.equal(ink.strokes.length, 1);
  assert.equal(ink.strokes[0].points[0].p, 0.5);
  ink.destroy();
});

test('read-only evidence cannot be modified by pencil, mouse, clear or undo', () => {
  const strokes = [{ points: [{ x: 0.2, y: 0.2, p: 0.5 }], width: 0.009 }];
  const ink = new InkCanvas(surface(), { strokes, readOnly: true });
  write(ink);
  ink.clear();
  ink.undo();
  assert.deepEqual(ink.strokes, strokes);
  ink.destroy();
});

test('coalesced pencil samples are captured, clipped to the answer area and committed on cancellation', () => {
  let changes = 0;
  const ink = new InkCanvas(surface(), { onChange: () => { changes += 1; } });
  ink.start(pointer(20, 20));
  ink.move(pointer(100, 100, { getCoalescedEvents: () => [pointer(30, 30), pointer(40, 40), pointer(450, -20)] }));
  ink.finish(pointer(450, -20, { type: 'pointercancel' }));
  assert.equal(ink.strokes[0].points.length, 4);
  assert.deepEqual(ink.strokes[0].points.at(-1), { x: 1, y: 0, p: 0.6 });
  assert.equal(changes, 1);
  ink.destroy();
});

test('long continuous handwriting stays below the server 4,000-point stroke limit', () => {
  const ink = new InkCanvas(surface());
  ink.start(pointer(0, 0));
  for (let index = 0; index < 20000; index += 1) ink.move(pointer(index % 400, index % 200));
  ink.finish(pointer(400, 200, { type: 'pointerup' }));
  assert.ok(ink.strokes[0].points.length <= 4000);
  assert.deepEqual(ink.strokes[0].points[0], { x: 0, y: 0, p: 0.6 });
  assert.deepEqual(ink.strokes[0].points.at(-1), { x: 1, y: 1, p: 0.6 });
  ink.destroy();
});

test('dense multi-stroke answers are resampled below the 20,000-point answer limit', () => {
  const strokes = Array.from({ length: 6 }, () => ({
    points: Array.from({ length: 3900 }, (_value, index) => ({ x: index / 3900, y: index / 3900, p: 0.6 })), width: 0.009,
  }));
  const ink = new InkCanvas(surface(), { strokes });
  write(ink);
  assert.equal(ink.strokes.length, 7);
  assert.ok(ink.strokes.reduce((sum, stroke) => sum + stroke.points.length, 0) <= 20000);
  assert.ok(ink.strokes.every((stroke) => stroke.points.length <= 4000));
  ink.destroy();
});

test('200-stroke limit gives feedback while erasing and undo remain usable', () => {
  let limits = 0;
  const strokes = Array.from({ length: 200 }, () => ({ points: [{ x: 0.2, y: 0.2, p: 0.5 }], width: 0.009 }));
  const ink = new InkCanvas(surface(), { strokes, onLimit: () => { limits += 1; } });
  ink.start(pointer(100, 100));
  assert.equal(ink.strokes.length, 200);
  assert.equal(limits, 1);
  ink.configure({ tool: 'eraser' });
  write(ink, [[80, 40], [80, 40]]);
  assert.equal(ink.strokes.length, 0);
  ink.undo();
  assert.equal(ink.strokes.length, 200);
  ink.destroy();
});

test('eraser detects a crossing between sparse samples and clear is undoable', () => {
  const ink = new InkCanvas(surface());
  write(ink, [[0, 100], [400, 100]]);
  ink.configure({ tool: 'eraser' });
  write(ink, [[200, 100], [200, 100]]);
  assert.equal(ink.strokes.length, 0);
  ink.undo();
  assert.equal(ink.strokes.length, 1);
  ink.clear();
  assert.equal(ink.strokes.length, 0);
  ink.undo();
  assert.equal(ink.strokes.length, 1);
  ink.destroy();
});

test('a new ruled pad and repeated redraws never create default ink', () => {
  let changes = 0;
  const ink = new InkCanvas(surface(), { onChange: () => { changes += 1; } });
  for (let i = 0; i < 10; i += 1) { ink.resize(); ink.setStrokes([]); }
  assert.deepEqual(ink.strokes, []);
  assert.equal(changes, 0);
  ink.destroy();
});

for (const pointerType of ['mouse', 'touch', 'pen']) {
  test(`${pointerType}: selecting another answer does not save a phantom dot`, () => {
    let changes = 0;
    const ink = new InkCanvas(surface(), { finger: true, selectOnTap: () => true, onChange: () => { changes += 1; } });
    for (let i = 0; i < 5; i += 1) {
      ink.start(pointer(100, 50, { pointerType }));
      ink.finish(pointer(101, 50, { pointerType, type: 'pointerup' }));
    }
    assert.deepEqual(ink.strokes, []);
    assert.equal(changes, 0);
    assert.equal(ink.undoStack.length, 0);
    ink.destroy();
  });

  test(`${pointerType}: the first drag selects and retains the complete first stroke`, () => {
    const ink = new InkCanvas(surface(), { finger: true, selectOnTap: () => true });
    ink.start(pointer(20, 20, { pointerType }));
    ink.move(pointer(40, 60, { pointerType }));
    ink.finish(pointer(80, 100, { pointerType, type: 'pointerup' }));
    assert.equal(ink.strokes.length, 1);
    assert.equal(ink.strokes[0].points.length, 3);
    assert.equal(ink.strokes[0].points[0].x, 0.05);
    assert.equal(ink.strokes[0].points.at(-1).x, 0.2);
    ink.destroy();
  });
}

test('deliberate decimal dots after field selection are preserved, including one-point dots', () => {
  let selected = false;
  const ink = new InkCanvas(surface(), { selectOnTap: () => !selected, onStart: () => { selected = true; } });
  ink.start(pointer(20, 20));
  ink.finish(pointer(20, 20, { type: 'pointerup' }));
  assert.equal(ink.strokes.length, 0);
  write(ink);
  ink.start(pointer(200, 170));
  ink.finish(pointer(200, 170, { type: 'pointerup' }));
  assert.equal(ink.strokes.length, 2);
  assert.equal(ink.strokes[1].points.length, 1);
  ink.undo();
  assert.equal(ink.strokes.length, 1);
  ink.destroy();
});

test('a cancelled stationary contact does not become a dot, but an intentional pad tap does', () => {
  let changes = 0;
  const ink = new InkCanvas(surface(), { onChange: () => { changes += 1; } });
  for (const type of ['pointercancel', 'lostpointercapture']) {
    ink.start(pointer(30, 30));
    ink.finish(pointer(30, 30, { type }));
  }
  assert.equal(ink.strokes.length, 0);
  assert.equal(changes, 0);
  ink.start(pointer(30, 30));
  ink.finish(pointer(30, 30, { type: 'pointerup' }));
  assert.equal(ink.strokes.length, 1);
  assert.equal(changes, 1);
  ink.destroy();
});
