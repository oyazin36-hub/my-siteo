// Parts list manager — tracks picked parts and their attributes
'use strict';

class PartsManager {
  constructor() {
    this.parts = [];
    this._nextId = 1;
    this._onChange = null;
  }

  onChange(fn) { this._onChange = fn; }

  addFromEntity(entity, dxf) {
    const dims = this._calcDimensions(entity, dxf);
    const layerName = entity.layer || '0';
    const { material, thickness } = this._guessFromLayer(layerName);

    // Check for duplicate handle
    const existing = this.parts.find(p => p.handle === entity.handle);
    if (existing) return existing;

    const part = {
      id: this._nextId++,
      handle: entity.handle,
      entityType: entity.type,
      layer: layerName,
      dims,
      material: material || '',
      thickness: thickness || '',
      quantity: 1,
      note: '',
      selected: false
    };
    this.parts.push(part);
    if (this._onChange) this._onChange(this.parts);
    return part;
  }

  updatePart(id, fields) {
    const part = this.parts.find(p => p.id === id);
    if (!part) return;
    Object.assign(part, fields);
    if (this._onChange) this._onChange(this.parts);
  }

  removePart(id) {
    this.parts = this.parts.filter(p => p.id !== id);
    if (this._onChange) this._onChange(this.parts);
  }

  clearAll() {
    this.parts = [];
    this._nextId = 1;
    if (this._onChange) this._onChange(this.parts);
  }

  getHandles() {
    return new Set(this.parts.map(p => p.handle));
  }

  // Estimate part dimensions from entity geometry
  _calcDimensions(entity, dxf) {
    switch (entity.type) {
      case 'LINE': {
        const dx = (entity.x2 || 0) - (entity.x1 || 0);
        const dy = (entity.y2 || 0) - (entity.y1 || 0);
        const len = Math.sqrt(dx * dx + dy * dy);
        return { length: this._round(len), width: null, radius: null };
      }
      case 'CIRCLE':
        return { length: null, width: null, radius: this._round(entity.r || 0), diameter: this._round((entity.r || 0) * 2) };
      case 'ARC': {
        const angle = ((entity.endAngle || 0) - (entity.startAngle || 0) + 360) % 360;
        const arcLen = (entity.r || 0) * angle * Math.PI / 180;
        return { length: this._round(arcLen), radius: this._round(entity.r || 0), angle: this._round(angle) };
      }
      case 'LWPOLYLINE': case 'POLYLINE': {
        if (!entity.vertices || entity.vertices.length < 2) return { length: null, width: null };
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        entity.vertices.forEach(v => {
          minX = Math.min(minX, v.x); maxX = Math.max(maxX, v.x);
          minY = Math.min(minY, v.y); maxY = Math.max(maxY, v.y);
        });
        return {
          length: this._round(maxX - minX),
          width: this._round(maxY - minY),
          perimeter: this._round(this._polyPerimeter(entity))
        };
      }
      default:
        return { length: null, width: null };
    }
  }

  _polyPerimeter(entity) {
    if (!entity.vertices || entity.vertices.length < 2) return 0;
    let total = 0;
    for (let i = 0; i + 1 < entity.vertices.length; i++) {
      const v1 = entity.vertices[i], v2 = entity.vertices[i + 1];
      total += Math.sqrt((v2.x - v1.x) ** 2 + (v2.y - v1.y) ** 2);
    }
    if (entity.closed) {
      const v1 = entity.vertices[entity.vertices.length - 1];
      const v2 = entity.vertices[0];
      total += Math.sqrt((v2.x - v1.x) ** 2 + (v2.y - v1.y) ** 2);
    }
    return total;
  }

  _round(v) { return Math.round(v * 100) / 100; }

  // Guess material and thickness from layer name
  // Common patterns: "SS400-9t", "SUS304-2.3t", "AL-1.5", "STEEL_6mm", "板厚6"
  _guessFromLayer(layerName) {
    const name = layerName.toUpperCase();
    let material = '';
    let thickness = '';

    // Material keywords
    if (/SS400/.test(name)) material = 'SS400';
    else if (/SUS304/.test(name)) material = 'SUS304';
    else if (/SUS316/.test(name)) material = 'SUS316';
    else if (/SUS/.test(name)) material = 'SUS';
    else if (/AL|ALUM/.test(name)) material = 'アルミ';
    else if (/CU|COPPER/.test(name)) material = '銅';
    else if (/SS|STEEL|鉄|鋼/.test(name)) material = 'SS400';

    // Thickness patterns: 6T, 6MM, 6t, t6, 板厚6
    const tMatch = name.match(/(\d+(?:\.\d+)?)[Tt](?:MM)?/) ||
                   name.match(/[Tt](\d+(?:\.\d+)?)/) ||
                   name.match(/(\d+(?:\.\d+)?)MM/);
    if (tMatch) thickness = tMatch[1] + 't';

    return { material, thickness };
  }

  // Format dimensions as human-readable string
  static formatDims(dims) {
    if (!dims) return '-';
    const parts = [];
    if (dims.length !== null && dims.length !== undefined) parts.push(`L=${dims.length}mm`);
    if (dims.width !== null && dims.width !== undefined) parts.push(`W=${dims.width}mm`);
    if (dims.diameter !== null && dims.diameter !== undefined) parts.push(`φ${dims.diameter}mm`);
    if (dims.radius !== null && dims.radius !== undefined && !dims.diameter) parts.push(`R=${dims.radius}mm`);
    if (dims.angle !== null && dims.angle !== undefined) parts.push(`${dims.angle}°`);
    if (dims.perimeter !== null && dims.perimeter !== undefined) parts.push(`P=${dims.perimeter}mm`);
    return parts.join(' × ') || '-';
  }

  // Export as CSV text
  toCsv() {
    const header = ['No.', '図形', 'レイヤ', '寸法', '材質', '板厚', '個数', '備考'];
    const rows = this.parts.map(p => [
      p.id,
      p.entityType,
      p.layer,
      PartsManager.formatDims(p.dims),
      p.material,
      p.thickness,
      p.quantity,
      p.note
    ]);
    return [header, ...rows].map(r => r.map(c => `"${c}"`).join(',')).join('\n');
  }
}
