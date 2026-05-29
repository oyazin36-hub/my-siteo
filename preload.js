const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  openDxfDialog: () => ipcRenderer.invoke('open-dxf-dialog'),
  printPdf: () => ipcRenderer.invoke('print-pdf'),
  onMenuEvent: (callback) => {
    ['menu-open-file', 'menu-print', 'menu-fit', 'menu-zoom-in', 'menu-zoom-out'].forEach(ch => {
      ipcRenderer.on(ch, () => callback(ch));
    });
  }
});
