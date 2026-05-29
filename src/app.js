// Main application controller
'use strict';

(function () {
  const parser = new DxfParser();
  const partsManager = new PartsManager();
  let renderer = null;
  let currentDxf = null;
  let pendingEntity = null;
  let selectMode = true;

  // Elements
  const canvas = document.getElementById('dxf-canvas');
  const canvasPane = document.getElementById('canvas-pane');
  const statusBar = document.getElementById('status-bar');
  const partsCount = document.getElementById('parts-count');
  const partsTbody = document.getElementById('parts-tbody');
  const partsEmpty = document.getElementById('parts-empty');
  const dialogOverlay = document.getElementById('dialog-overlay');
  const partForm = document.getElementById('part-form');
  const printTbody = document.getElementById('print-tbody');
  const printMeta = document.getElementById('print-meta');
  const printDate = document.getElementById('print-date');

  // Init canvas size
  function resizeCanvas() {
    const rect = canvasPane.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    if (renderer) renderer.render();
  }

  function initRenderer() {
    renderer = new DxfRenderer(canvas);
    renderer.onSelect((entity, shiftKey) => {
      if (!selectMode) return;
      if (currentDxf) openDialog(entity);
    });
  }

  // ---- File open ----
  async function openFile() {
    const result = await window.api.openDxfDialog();
    if (!result || result.error) {
      if (result && result.error) setStatus('エラー: ' + result.error);
      return;
    }
    setStatus('DXF解析中...');
    try {
      currentDxf = parser.parse(result.content);
      renderer.load(currentDxf);
      const fname = result.filePath.split(/[\\/]/).pop();
      setStatus(`${fname}  —  エンティティ: ${currentDxf.entities.length}個`);
      printMeta.textContent = '図面: ' + fname;
    } catch (e) {
      setStatus('解析エラー: ' + e.message);
      console.error(e);
    }
  }

  // ---- Parts dialog ----
  function openDialog(entity) {
    pendingEntity = entity;
    const dims = partsManager._calcDimensions(entity, currentDxf);
    const layerName = entity.layer || '0';
    const { material, thickness } = partsManager._guessFromLayer(layerName);

    document.getElementById('f-dims').value = PartsManager.formatDims(dims);
    document.getElementById('f-material').value = '';
    document.getElementById('f-material-custom').value = material || '';
    document.getElementById('f-thickness').value = '';
    document.getElementById('f-thickness-custom').value = thickness || '';
    document.getElementById('f-quantity').value = 1;
    document.getElementById('f-note').value = '';

    // Pre-select dropdown if matches
    const matSel = document.getElementById('f-material');
    for (const opt of matSel.options) {
      if (opt.value === material) { matSel.value = material; break; }
    }
    const thkSel = document.getElementById('f-thickness');
    for (const opt of thkSel.options) {
      if (opt.value === thickness) { thkSel.value = thickness; break; }
    }

    dialogOverlay.classList.remove('hidden');
    document.getElementById('f-quantity').focus();
  }

  function closeDialog() {
    dialogOverlay.classList.add('hidden');
    pendingEntity = null;
  }

  function getMaterial() {
    const sel = document.getElementById('f-material').value;
    const custom = document.getElementById('f-material-custom').value.trim();
    return custom || sel;
  }

  function getThickness() {
    const sel = document.getElementById('f-thickness').value;
    const custom = document.getElementById('f-thickness-custom').value.trim();
    return custom || sel;
  }

  partForm.addEventListener('submit', e => {
    e.preventDefault();
    if (!pendingEntity) return;

    const dims = partsManager._calcDimensions(pendingEntity, currentDxf);
    const part = {
      id: partsManager._nextId++,
      handle: pendingEntity.handle,
      entityType: pendingEntity.type,
      layer: pendingEntity.layer || '0',
      dims,
      material: getMaterial(),
      thickness: getThickness(),
      quantity: parseInt(document.getElementById('f-quantity').value, 10) || 1,
      note: document.getElementById('f-note').value.trim()
    };

    // Avoid duplicate handles
    if (pendingEntity.handle && partsManager.parts.some(p => p.handle === pendingEntity.handle)) {
      closeDialog();
      setStatus('このエンティティはすでにリストにあります');
      return;
    }

    partsManager.parts.push(part);
    renderer.selectedHandles.add(pendingEntity.handle);
    renderer.render();
    renderPartsTable();
    closeDialog();
    setStatus(`部品 No.${part.id} を追加しました（合計 ${partsManager.parts.length}件）`);
  });

  document.getElementById('dialog-cancel').addEventListener('click', closeDialog);
  dialogOverlay.addEventListener('click', e => { if (e.target === dialogOverlay) closeDialog(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDialog(); });

  // ---- Parts table rendering ----
  function renderPartsTable() {
    const parts = partsManager.parts;
    partsEmpty.style.display = parts.length ? 'none' : 'block';
    partsCount.textContent = `(${parts.length}件)`;

    partsTbody.innerHTML = '';
    parts.forEach(part => {
      const tr = document.createElement('tr');
      tr.dataset.id = part.id;

      tr.innerHTML = `
        <td>${part.id}</td>
        <td>${part.entityType}</td>
        <td title="${part.layer}">${part.layer.length > 10 ? part.layer.slice(0, 10) + '…' : part.layer}</td>
        <td style="font-size:11px;white-space:nowrap">${PartsManager.formatDims(part.dims)}</td>
        <td><input type="text" value="${esc(part.material)}" data-field="material" data-id="${part.id}"></td>
        <td><input type="text" value="${esc(part.thickness)}" data-field="thickness" data-id="${part.id}" style="width:60px"></td>
        <td><input type="number" value="${part.quantity}" min="1" data-field="quantity" data-id="${part.id}" style="width:50px"></td>
        <td><input type="text" value="${esc(part.note)}" data-field="note" data-id="${part.id}"></td>
        <td><button class="btn-row-delete" data-id="${part.id}" title="削除">×</button></td>
      `;
      partsTbody.appendChild(tr);
    });

    // Inline edit listeners
    partsTbody.querySelectorAll('input').forEach(input => {
      input.addEventListener('change', e => {
        const id = parseInt(e.target.dataset.id, 10);
        const field = e.target.dataset.field;
        const val = field === 'quantity' ? (parseInt(e.target.value, 10) || 1) : e.target.value;
        partsManager.updatePart(id, { [field]: val });
      });
    });

    // Delete buttons
    partsTbody.querySelectorAll('.btn-row-delete').forEach(btn => {
      btn.addEventListener('click', e => {
        const id = parseInt(btn.dataset.id, 10);
        const part = partsManager.parts.find(p => p.id === id);
        if (part && part.handle) {
          renderer.selectedHandles.delete(part.handle);
          renderer.render();
        }
        partsManager.removePart(id);
        renderPartsTable();
      });
    });

    updateSummary();
  }

  function updateSummary() {
    const total = partsManager.parts.reduce((s, p) => s + (p.quantity || 1), 0);
    document.getElementById('parts-summary').textContent = `合計 ${partsManager.parts.length}種 / ${total}個`;
  }

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  // ---- Print ----
  function preparePrint() {
    printDate.textContent = new Date().toLocaleDateString('ja-JP');
    printTbody.innerHTML = '';
    partsManager.parts.forEach(part => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${part.id}</td>
        <td>${part.entityType}</td>
        <td>${part.layer}</td>
        <td>${PartsManager.formatDims(part.dims)}</td>
        <td>${esc(part.material)}</td>
        <td>${esc(part.thickness)}</td>
        <td>${part.quantity}</td>
        <td>${esc(part.note)}</td>
      `;
      printTbody.appendChild(tr);
    });
    window.print();
  }

  // ---- CSV Export ----
  function exportCsv() {
    const csv = partsManager.toCsv();
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'zumen-pickup-' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---- Resizer drag ----
  function initResizer() {
    const resizer = document.getElementById('resizer');
    const partsPane = document.getElementById('parts-pane');
    let dragging = false, startX = 0, startW = 0;

    resizer.addEventListener('mousedown', e => {
      dragging = true;
      startX = e.clientX;
      startW = partsPane.offsetWidth;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });
    window.addEventListener('mousemove', e => {
      if (!dragging) return;
      const delta = startX - e.clientX;
      const newW = Math.max(280, Math.min(800, startW + delta));
      partsPane.style.width = newW + 'px';
      resizeCanvas();
    });
    window.addEventListener('mouseup', () => {
      if (dragging) {
        dragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }

  // ---- Toolbar buttons ----
  document.getElementById('btn-open').addEventListener('click', openFile);
  document.getElementById('btn-fit').addEventListener('click', () => renderer && renderer.fitAll());
  document.getElementById('btn-zoom-in').addEventListener('click', () => renderer && renderer.zoom(1.3));
  document.getElementById('btn-zoom-out').addEventListener('click', () => renderer && renderer.zoom(1 / 1.3));
  document.getElementById('btn-clear-parts').addEventListener('click', () => {
    if (!partsManager.parts.length) return;
    if (confirm('拾い出しリストをクリアしますか？')) {
      partsManager.clearAll();
      if (renderer) { renderer.selectedHandles.clear(); renderer.render(); }
      renderPartsTable();
    }
  });
  document.getElementById('btn-print').addEventListener('click', preparePrint);
  document.getElementById('btn-export-csv').addEventListener('click', exportCsv);
  document.getElementById('chk-select-mode').addEventListener('change', e => {
    selectMode = e.target.checked;
    canvas.style.cursor = selectMode ? 'crosshair' : 'default';
  });

  // Menu events from main process
  window.api.onMenuEvent(event => {
    switch (event) {
      case 'menu-open-file': openFile(); break;
      case 'menu-print': preparePrint(); break;
      case 'menu-fit': renderer && renderer.fitAll(); break;
      case 'menu-zoom-in': renderer && renderer.zoom(1.3); break;
      case 'menu-zoom-out': renderer && renderer.zoom(1 / 1.3); break;
    }
  });

  function setStatus(msg) { statusBar.textContent = msg; }

  // ---- Init ----
  initRenderer();
  initResizer();
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
  new ResizeObserver(resizeCanvas).observe(canvasPane);
})();
