// DXF Canvas Renderer — pure JS, uses browser's HTMLCanvasElement
'use strict';

// AutoCAD color index → RGB
const ACI_COLORS = [
  '#000000','#FF0000','#FFFF00','#00FF00','#00FFFF','#0000FF','#FF00FF','#FFFFFF',
  '#414141','#808080','#FF0000','#FFAAAA','#BD0000','#BD7E7E','#810000','#815656',
  '#680000','#684545','#4F0000','#4F3535','#FF3F00','#FFBFAA','#BD2E00','#BD8D7E',
  '#811F00','#816056','#681900','#684E45','#4F1300','#4F3B35','#FF7F00','#FFD4AA',
  '#BD5E00','#BD9D7E','#814000','#816B56','#683400','#685645','#4F2700','#4F4235',
  '#FFBF00','#FFEAAA','#BD8D00','#BDAD7E','#816000','#817656','#684E00','#685F45',
  '#4F3B00','#4F4935','#FFFF00','#FFFF AA','#BDBD00','#BDBD7E','#818100','#818156',
  '#686800','#686845','#4F4F00','#4F4F35','#BFFF00','#EAFFAA','#8DBD00','#ADBD7E',
  '#608100','#768156','#4E6800','#5F6845','#3B4F00','#494F35','#7FFF00','#D4FFAA',
  '#5EBD00','#9DBD7E','#408100','#6B8156','#346800','#566845','#274F00','#424F35',
  '#3FFF00','#BFFFAA','#2EBD00','#8DBD7E','#1F8100','#608156','#196800','#4E6845',
  '#134F00','#3B4F35','#00FF00','#AAFFAA','#00BD00','#7EBD7E','#008100','#568156',
  '#006800','#456845','#004F00','#354F35','#00FF3F','#AAFFBF','#00BD2E','#7EBD8D',
  '#00811F','#568160','#006819','#45684E','#004F13','#354F3B','#00FF7F','#AAFFD4',
  '#00BD5E','#7EBD9D','#008140','#56816B','#006834','#456856','#004F27','#354F42',
  '#00FFBF','#AAFFEA','#00BD8D','#7EBDAD','#008160','#568176','#00684E','#45685F',
  '#004F3B','#354F49','#00FFFF','#AAFFFF','#00BDBD','#7EBDBD','#008181','#568181',
  '#006868','#456868','#004F4F','#354F4F','#00BFFF','#AAEAFF','#008DBD','#7EADBD',
  '#006081','#567681','#004E68','#455F68','#003B4F','#35494F','#007FFF','#AAD4FF',
  '#005EBD','#7E9DBD','#004081','#566B81','#003468','#455668','#00274F','#35424F',
  '#003FFF','#AABFFF','#002EBD','#7E8DBD','#001F81','#566081','#001968','#454E68',
  '#00134F','#353B4F','#0000FF','#AAAAFF','#0000BD','#7E7EBD','#000081','#565681',
  '#000068','#454568','#00004F','#35354F','#3F00FF','#BFAAFF','#2E00BD','#8D7EBD',
  '#1F0081','#605681','#190068','#4E4568','#13004F','#3B354F','#7F00FF','#D4AAFF',
  '#5E00BD','#9D7EBD','#400081','#6B5681','#340068','#564568','#27004F','#42354F',
  '#BF00FF','#EAAAFF','#8D00BD','#AD7EBD','#600081','#765681','#4E0068','#5F4568',
  '#3B004F','#49354F','#FF00FF','#FFAAFF','#BD00BD','#BD7EBD','#810081','#815681',
  '#680068','#684568','#4F004F','#4F354F','#FF00BF','#FFAAEA','#BD008D','#BD7EAD',
  '#810060','#815676','#68004E','#68455F','#4F003B','#4F3549','#FF007F','#FFAAD4',
  '#BD005E','#BD7E9D','#810040','#81566B','#680034','#684556','#4F0027','#4F3542',
  '#FF003F','#FFAABF','#BD002E','#BD7E8D','#81001F','#815660','#680019','#68454E',
  '#4F0013','#4F353B','#333333','#505050','#696969','#828282','#BEBEBE','#FFFFFF'
];

function aciToRgb(index) {
  if (index === null || index === undefined) return '#FFFFFF';
  if (index === 7) return '#FFFFFF';
  return ACI_COLORS[index] || '#FFFFFF';
}

class DxfRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.dxf = null;
    this.viewX = 0;
    this.viewY = 0;
    this.scale = 1;
    this.selectedHandles = new Set();
    this.highlightedHandles = new Set();
    this.bgColor = '#1a1a2e';
    this._dragging = false;
    this._lastMX = 0;
    this._lastMY = 0;
    this._onSelect = null;
    this._setupEvents();
  }

  load(dxf) {
    this.dxf = dxf;
    this.selectedHandles.clear();
    this.fitAll();
  }

  onSelect(fn) { this._onSelect = fn; }

  fitAll() {
    if (!this.dxf) return;
    const b = this.dxf.bounds;
    const pw = this.canvas.width, ph = this.canvas.height;
    const margin = 40;
    const sx = (pw - margin * 2) / (b.width || 1);
    const sy = (ph - margin * 2) / (b.height || 1);
    this.scale = Math.min(sx, sy);
    this.viewX = pw / 2 - (b.minX + b.width / 2) * this.scale;
    this.viewY = ph / 2 + (b.minY + b.height / 2) * this.scale;
    this.render();
  }

  zoom(factor, cx, cy) {
    if (cx === undefined) { cx = this.canvas.width / 2; cy = this.canvas.height / 2; }
    const wx = (cx - this.viewX) / this.scale;
    const wy = (cy - this.viewY) / this.scale;
    this.scale *= factor;
    this.scale = Math.max(0.001, Math.min(1000, this.scale));
    this.viewX = cx - wx * this.scale;
    this.viewY = cy + wy * this.scale;
    this.render();
  }

  worldToScreen(wx, wy) {
    return { x: wx * this.scale + this.viewX, y: -wy * this.scale + this.viewY };
  }

  screenToWorld(sx, sy) {
    return { x: (sx - this.viewX) / this.scale, y: -(sy - this.viewY) / this.scale };
  }

  render() {
    const ctx = this.ctx;
    const w = this.canvas.width, h = this.canvas.height;
    ctx.fillStyle = this.bgColor;
    ctx.fillRect(0, 0, w, h);
    if (!this.dxf) return;

    ctx.save();
    ctx.translate(this.viewX, this.viewY);
    ctx.scale(this.scale, -this.scale);

    for (const entity of this.dxf.entities) {
      this._drawEntity(ctx, entity);
    }

    // Draw INSERT blocks
    for (const entity of this.dxf.entities) {
      if (entity.type === 'INSERT') this._drawInsert(ctx, entity);
    }

    ctx.restore();
  }

  _getEntityColor(entity) {
    const selected = this.selectedHandles.has(entity.handle);
    const highlighted = this.highlightedHandles.has(entity.handle);
    if (selected) return '#00FF88';
    if (highlighted) return '#FFDD00';

    if (entity.color !== null && entity.color !== undefined) return aciToRgb(entity.color);
    const layer = this.dxf.layers[entity.layer];
    if (layer) return aciToRgb(layer.color);
    return '#FFFFFF';
  }

  _drawEntity(ctx, entity, offsetX = 0, offsetY = 0) {
    const color = this._getEntityColor(entity);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1 / this.scale;

    switch (entity.type) {
      case 'LINE':
        ctx.beginPath();
        ctx.moveTo((entity.x1 || 0) + offsetX, (entity.y1 || 0) + offsetY);
        ctx.lineTo((entity.x2 || 0) + offsetX, (entity.y2 || 0) + offsetY);
        ctx.stroke();
        break;

      case 'CIRCLE':
        ctx.beginPath();
        ctx.arc((entity.cx || 0) + offsetX, (entity.cy || 0) + offsetY, entity.r || 0, 0, Math.PI * 2);
        ctx.stroke();
        break;

      case 'ARC': {
        const sa = -((entity.startAngle || 0) * Math.PI / 180);
        const ea = -((entity.endAngle || 0) * Math.PI / 180);
        ctx.beginPath();
        ctx.arc((entity.cx || 0) + offsetX, (entity.cy || 0) + offsetY, entity.r || 0, sa, ea, true);
        ctx.stroke();
        break;
      }

      case 'LWPOLYLINE':
      case 'POLYLINE':
        if (entity.vertices && entity.vertices.length > 1) {
          ctx.beginPath();
          ctx.moveTo(entity.vertices[0].x + offsetX, entity.vertices[0].y + offsetY);
          for (let i = 0; i < entity.vertices.length; i++) {
            const v = entity.vertices[i];
            const vNext = entity.vertices[(i + 1) % entity.vertices.length];
            if (v.bulge && Math.abs(v.bulge) > 0.0001 && (i + 1 < entity.vertices.length || entity.closed)) {
              this._drawBulgeArc(ctx, v, vNext, v.bulge, offsetX, offsetY);
            } else if (i + 1 < entity.vertices.length) {
              ctx.lineTo(vNext.x + offsetX, vNext.y + offsetY);
            }
          }
          if (entity.closed) ctx.closePath();
          ctx.stroke();
        }
        break;

      case 'SOLID': case 'TRACE':
        ctx.beginPath();
        ctx.moveTo((entity.x1 || 0) + offsetX, (entity.y1 || 0) + offsetY);
        ctx.lineTo((entity.x2 || 0) + offsetX, (entity.y2 || 0) + offsetY);
        ctx.lineTo((entity.x4 || entity.x3 || 0) + offsetX, (entity.y4 || entity.y3 || 0) + offsetY);
        ctx.lineTo((entity.x3 || 0) + offsetX, (entity.y3 || 0) + offsetY);
        ctx.closePath();
        ctx.fill();
        break;

      case 'TEXT': case 'MTEXT': {
        const h = (entity.height || 2.5) * 0.8;
        ctx.save();
        ctx.scale(1, -1);
        ctx.font = `${h}px monospace`;
        ctx.textBaseline = 'alphabetic';
        ctx.fillText(entity.text || '', (entity.x || 0) + offsetX, -(entity.y || 0) - offsetY);
        ctx.restore();
        break;
      }

      case 'ELLIPSE': {
        const rx = Math.sqrt((entity.majorX || 0) ** 2 + (entity.majorY || 0) ** 2);
        const ry = rx * (entity.ratio || 1);
        const rot = Math.atan2(entity.majorY || 0, entity.majorX || 0);
        ctx.save();
        ctx.translate((entity.cx || 0) + offsetX, (entity.cy || 0) + offsetY);
        ctx.rotate(-rot);
        ctx.beginPath();
        ctx.ellipse(0, 0, rx, ry, 0, -(entity.endAngle || Math.PI * 2), -(entity.startAngle || 0), true);
        ctx.restore();
        ctx.stroke();
        break;
      }
    }
  }

  _drawBulgeArc(ctx, v1, v2, bulge, ox, oy) {
    const dx = v2.x - v1.x, dy = v2.y - v1.y;
    const d = Math.sqrt(dx * dx + dy * dy);
    const r = d / (2 * Math.sin(2 * Math.atan(Math.abs(bulge))));
    const mx = (v1.x + v2.x) / 2, my = (v1.y + v2.y) / 2;
    const sagitta = r - Math.sqrt(r * r - (d / 2) * (d / 2));
    const sign = bulge > 0 ? 1 : -1;
    const nx = -dy / d, ny = dx / d;
    const cx = mx + sign * sagitta * nx;
    const cy = my + sign * sagitta * ny;
    const startAngle = Math.atan2(v1.y - cy, v1.x - cx);
    const endAngle = Math.atan2(v2.y - cy, v2.x - cx);
    ctx.arc(cx + ox, cy + oy, r, startAngle, endAngle, bulge < 0);
  }

  _drawInsert(ctx, entity) {
    const block = this.dxf.blocks[entity.blockName];
    if (!block) return;
    const sx = entity.scaleX || 1, sy = entity.scaleY || 1;
    const rot = ((entity.rotation || 0) * Math.PI) / 180;
    ctx.save();
    ctx.translate(entity.x || 0, entity.y || 0);
    ctx.rotate(-rot);
    ctx.scale(sx, sy);
    for (const e of block.entities) this._drawEntity(ctx, e);
    ctx.restore();
  }

  // Hit-test: find closest entity to a screen point
  hitTest(sx, sy, threshold = 10) {
    if (!this.dxf) return null;
    const w = this.screenToWorld(sx, sy);
    const wt = threshold / this.scale;
    let best = null, bestDist = Infinity;

    for (const entity of this.dxf.entities) {
      const d = this._distEntity(entity, w.x, w.y);
      if (d < wt && d < bestDist) { best = entity; bestDist = d; }
    }
    return best;
  }

  _distEntity(entity, wx, wy) {
    switch (entity.type) {
      case 'LINE': return this._distSegment(wx, wy, entity.x1 || 0, entity.y1 || 0, entity.x2 || 0, entity.y2 || 0);
      case 'CIRCLE': return Math.abs(Math.sqrt((wx - entity.cx) ** 2 + (wy - entity.cy) ** 2) - entity.r);
      case 'ARC': {
        const d = Math.sqrt((wx - entity.cx) ** 2 + (wy - entity.cy) ** 2);
        return Math.abs(d - entity.r);
      }
      case 'LWPOLYLINE': case 'POLYLINE': {
        if (!entity.vertices || !entity.vertices.length) return Infinity;
        let min = Infinity;
        for (let i = 0; i + 1 < entity.vertices.length; i++) {
          const d = this._distSegment(wx, wy, entity.vertices[i].x, entity.vertices[i].y, entity.vertices[i + 1].x, entity.vertices[i + 1].y);
          if (d < min) min = d;
        }
        if (entity.closed && entity.vertices.length > 2) {
          const last = entity.vertices.length - 1;
          const d = this._distSegment(wx, wy, entity.vertices[last].x, entity.vertices[last].y, entity.vertices[0].x, entity.vertices[0].y);
          if (d < min) min = d;
        }
        return min;
      }
      case 'TEXT': case 'MTEXT':
        return Math.sqrt((wx - entity.x) ** 2 + (wy - entity.y) ** 2);
      default:
        return Infinity;
    }
  }

  _distSegment(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay;
    const len2 = dx * dx + dy * dy;
    if (len2 < 1e-10) return Math.sqrt((px - ax) ** 2 + (py - ay) ** 2);
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
    return Math.sqrt((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2);
  }

  _setupEvents() {
    const c = this.canvas;

    c.addEventListener('wheel', e => {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.zoom(factor, e.clientX - rect.left, e.clientY - rect.top);
    }, { passive: false });

    c.addEventListener('mousedown', e => {
      if (e.button === 1 || e.button === 2) {
        this._dragging = true;
        this._lastMX = e.clientX;
        this._lastMY = e.clientY;
        c.style.cursor = 'grabbing';
      }
    });

    window.addEventListener('mousemove', e => {
      if (!this._dragging) return;
      const dx = e.clientX - this._lastMX;
      const dy = e.clientY - this._lastMY;
      this.viewX += dx;
      this.viewY += dy;
      this._lastMX = e.clientX;
      this._lastMY = e.clientY;
      this.render();
    });

    window.addEventListener('mouseup', e => {
      if (this._dragging) {
        this._dragging = false;
        c.style.cursor = 'crosshair';
      }
    });

    c.addEventListener('click', e => {
      const rect = c.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const hit = this.hitTest(sx, sy);
      if (hit && this._onSelect) this._onSelect(hit, e.shiftKey);
    });

    c.addEventListener('contextmenu', e => e.preventDefault());
  }

  resize(w, h) {
    this.canvas.width = w;
    this.canvas.height = h;
    this.render();
  }
}
