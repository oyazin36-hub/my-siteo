// Pure JS DXF parser — no external dependencies
'use strict';

class DxfParser {
  parse(text) {
    const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const pairs = [];
    for (let i = 0; i + 1 < lines.length; i += 2) {
      pairs.push({ code: parseInt(lines[i].trim(), 10), value: lines[i + 1] ? lines[i + 1].trim() : '' });
    }

    const result = {
      layers: {},
      entities: [],
      blocks: {},
      header: {}
    };

    let i = 0;

    // Find HEADER section
    i = this._findSection(pairs, 'HEADER');
    if (i >= 0) this._parseHeader(pairs, i, result.header);

    // Find TABLES section (layers)
    i = this._findSection(pairs, 'TABLES');
    if (i >= 0) this._parseTables(pairs, i, result.layers);

    // Find BLOCKS section
    i = this._findSection(pairs, 'BLOCKS');
    if (i >= 0) this._parseBlocks(pairs, i, result.blocks);

    // Find ENTITIES section
    i = this._findSection(pairs, 'ENTITIES');
    if (i >= 0) this._parseEntities(pairs, i, result.entities);

    result.bounds = this._calcBounds(result.entities, result.blocks);
    return result;
  }

  _findSection(pairs, name) {
    for (let i = 0; i < pairs.length; i++) {
      if (pairs[i].code === 0 && pairs[i].value === 'SECTION') {
        if (pairs[i + 1] && pairs[i + 1].code === 2 && pairs[i + 1].value === name) {
          return i + 2;
        }
      }
    }
    return -1;
  }

  _parseHeader(pairs, start, header) {
    for (let i = start; i < pairs.length; i++) {
      if (pairs[i].code === 0 && pairs[i].value === 'ENDSEC') break;
      if (pairs[i].code === 9) {
        const varName = pairs[i].value;
        const vals = {};
        let j = i + 1;
        while (j < pairs.length && pairs[j].code !== 9 && pairs[j].code !== 0) {
          vals[pairs[j].code] = pairs[j].value;
          j++;
        }
        header[varName] = vals;
      }
    }
  }

  _parseTables(pairs, start, layers) {
    let i = start;
    while (i < pairs.length) {
      if (pairs[i].code === 0 && pairs[i].value === 'ENDSEC') break;
      if (pairs[i].code === 0 && pairs[i].value === 'LAYER') {
        const layer = { name: '', color: 7, lineType: 'CONTINUOUS', on: true };
        i++;
        while (i < pairs.length && pairs[i].code !== 0) {
          switch (pairs[i].code) {
            case 2: layer.name = pairs[i].value; break;
            case 62: layer.color = Math.abs(parseInt(pairs[i].value, 10));
                     layer.on = parseInt(pairs[i].value, 10) >= 0; break;
            case 6: layer.lineType = pairs[i].value; break;
          }
          i++;
        }
        if (layer.name) layers[layer.name] = layer;
        continue;
      }
      i++;
    }
  }

  _parseBlocks(pairs, start, blocks) {
    let i = start;
    let currentBlock = null;
    while (i < pairs.length) {
      if (pairs[i].code === 0 && pairs[i].value === 'ENDSEC') break;
      if (pairs[i].code === 0 && pairs[i].value === 'BLOCK') {
        currentBlock = { name: '', entities: [], x: 0, y: 0 };
        i++;
        while (i < pairs.length && pairs[i].code !== 0) {
          if (pairs[i].code === 2) currentBlock.name = pairs[i].value;
          if (pairs[i].code === 10) currentBlock.x = parseFloat(pairs[i].value);
          if (pairs[i].code === 20) currentBlock.y = parseFloat(pairs[i].value);
          i++;
        }
        continue;
      }
      if (pairs[i].code === 0 && pairs[i].value === 'ENDBLK') {
        if (currentBlock && currentBlock.name && !currentBlock.name.startsWith('*')) {
          blocks[currentBlock.name] = currentBlock;
        }
        currentBlock = null;
        i++;
        continue;
      }
      if (currentBlock && pairs[i].code === 0) {
        const entity = this._parseEntity(pairs, i);
        if (entity) {
          currentBlock.entities.push(entity.entity);
          i = entity.nextIndex;
          continue;
        }
      }
      i++;
    }
  }

  _parseEntities(pairs, start, entities) {
    let i = start;
    while (i < pairs.length) {
      if (pairs[i].code === 0 && pairs[i].value === 'ENDSEC') break;
      if (pairs[i].code === 0) {
        const result = this._parseEntity(pairs, i);
        if (result) {
          entities.push(result.entity);
          i = result.nextIndex;
          continue;
        }
      }
      i++;
    }
  }

  _parseEntity(pairs, start) {
    const type = pairs[start].value;
    const supported = ['LINE','CIRCLE','ARC','LWPOLYLINE','POLYLINE','VERTEX','TEXT','MTEXT','INSERT','SOLID','TRACE','ELLIPSE','SPLINE','DIMENSION'];
    if (!supported.includes(type)) return null;

    const entity = {
      type,
      layer: '0',
      color: null,
      handle: null
    };

    let i = start + 1;

    // Common attributes
    while (i < pairs.length && !(pairs[i].code === 0)) {
      const { code, value } = pairs[i];
      switch (code) {
        case 8: entity.layer = value; break;
        case 5: entity.handle = value; break;
        case 62: entity.color = Math.abs(parseInt(value, 10)); break;
      }

      // Type-specific
      switch (entity.type) {
        case 'LINE':
          if (code === 10) entity.x1 = parseFloat(value);
          else if (code === 20) entity.y1 = parseFloat(value);
          else if (code === 11) entity.x2 = parseFloat(value);
          else if (code === 21) entity.y2 = parseFloat(value);
          break;

        case 'CIRCLE':
          if (code === 10) entity.cx = parseFloat(value);
          else if (code === 20) entity.cy = parseFloat(value);
          else if (code === 40) entity.r = parseFloat(value);
          break;

        case 'ARC':
          if (code === 10) entity.cx = parseFloat(value);
          else if (code === 20) entity.cy = parseFloat(value);
          else if (code === 40) entity.r = parseFloat(value);
          else if (code === 50) entity.startAngle = parseFloat(value);
          else if (code === 51) entity.endAngle = parseFloat(value);
          break;

        case 'ELLIPSE':
          if (code === 10) entity.cx = parseFloat(value);
          else if (code === 20) entity.cy = parseFloat(value);
          else if (code === 11) entity.majorX = parseFloat(value);
          else if (code === 21) entity.majorY = parseFloat(value);
          else if (code === 40) entity.ratio = parseFloat(value);
          else if (code === 41) entity.startAngle = parseFloat(value);
          else if (code === 42) entity.endAngle = parseFloat(value);
          break;

        case 'LWPOLYLINE':
          if (!entity.vertices) entity.vertices = [];
          if (code === 90) entity.vertexCount = parseInt(value, 10);
          else if (code === 70) entity.flags = parseInt(value, 10);
          else if (code === 10) entity.vertices.push({ x: parseFloat(value), y: 0, bulge: 0 });
          else if (code === 20 && entity.vertices.length) entity.vertices[entity.vertices.length - 1].y = parseFloat(value);
          else if (code === 42 && entity.vertices.length) entity.vertices[entity.vertices.length - 1].bulge = parseFloat(value);
          break;

        case 'POLYLINE':
          if (code === 70) entity.flags = parseInt(value, 10);
          if (!entity.vertices) entity.vertices = [];
          break;

        case 'VERTEX':
          if (code === 10) entity.x = parseFloat(value);
          else if (code === 20) entity.y = parseFloat(value);
          else if (code === 42) entity.bulge = parseFloat(value) || 0;
          break;

        case 'TEXT':
          if (code === 1) entity.text = value;
          else if (code === 10) entity.x = parseFloat(value);
          else if (code === 20) entity.y = parseFloat(value);
          else if (code === 40) entity.height = parseFloat(value);
          else if (code === 50) entity.rotation = parseFloat(value);
          break;

        case 'MTEXT':
          if (code === 1) entity.text = value.replace(/\\P/g, '\n').replace(/\\[a-zA-Z0-9;:.,]+/g, '').replace(/[{}]/g, '');
          else if (code === 10) entity.x = parseFloat(value);
          else if (code === 20) entity.y = parseFloat(value);
          else if (code === 40) entity.height = parseFloat(value);
          else if (code === 50) entity.rotation = parseFloat(value);
          break;

        case 'INSERT':
          if (code === 2) entity.blockName = value;
          else if (code === 10) entity.x = parseFloat(value);
          else if (code === 20) entity.y = parseFloat(value);
          else if (code === 41) entity.scaleX = parseFloat(value);
          else if (code === 42) entity.scaleY = parseFloat(value);
          else if (code === 50) entity.rotation = parseFloat(value);
          break;

        case 'SOLID':
        case 'TRACE':
          if (code === 10) entity.x1 = parseFloat(value);
          else if (code === 20) entity.y1 = parseFloat(value);
          else if (code === 11) entity.x2 = parseFloat(value);
          else if (code === 21) entity.y2 = parseFloat(value);
          else if (code === 12) entity.x3 = parseFloat(value);
          else if (code === 22) entity.y3 = parseFloat(value);
          else if (code === 13) entity.x4 = parseFloat(value);
          else if (code === 23) entity.y4 = parseFloat(value);
          break;

        case 'DIMENSION':
          if (code === 1) entity.text = value;
          else if (code === 10) entity.defX = parseFloat(value);
          else if (code === 20) entity.defY = parseFloat(value);
          else if (code === 11) entity.midX = parseFloat(value);
          else if (code === 21) entity.midY = parseFloat(value);
          else if (code === 70) entity.dimType = parseInt(value, 10);
          break;
      }
      i++;
    }

    // LWPOLYLINE closed flag
    if (entity.type === 'LWPOLYLINE') {
      entity.closed = !!(entity.flags & 1);
    }

    return { entity, nextIndex: i };
  }

  _calcBounds(entities, blocks) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    const expand = (x, y) => {
      if (isNaN(x) || isNaN(y)) return;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    };

    const processEntity = (e) => {
      switch (e.type) {
        case 'LINE':
          expand(e.x1, e.y1); expand(e.x2, e.y2); break;
        case 'CIRCLE':
          expand(e.cx - e.r, e.cy - e.r); expand(e.cx + e.r, e.cy + e.r); break;
        case 'ARC':
          expand(e.cx - e.r, e.cy - e.r); expand(e.cx + e.r, e.cy + e.r); break;
        case 'LWPOLYLINE':
        case 'POLYLINE':
          if (e.vertices) e.vertices.forEach(v => expand(v.x, v.y)); break;
        case 'TEXT':
        case 'MTEXT':
          expand(e.x, e.y); break;
        case 'INSERT':
          expand(e.x, e.y); break;
        case 'SOLID': case 'TRACE':
          expand(e.x1, e.y1); expand(e.x2, e.y2);
          expand(e.x3, e.y3); expand(e.x4, e.y4); break;
        case 'ELLIPSE':
          expand(e.cx - Math.abs(e.majorX), e.cy - Math.abs(e.majorX));
          expand(e.cx + Math.abs(e.majorX), e.cy + Math.abs(e.majorX)); break;
      }
    };

    entities.forEach(processEntity);
    Object.values(blocks).forEach(b => b.entities.forEach(processEntity));

    if (!isFinite(minX)) return { minX: 0, minY: 0, maxX: 100, maxY: 100, width: 100, height: 100 };
    return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
  }
}

if (typeof module !== 'undefined') module.exports = DxfParser;
