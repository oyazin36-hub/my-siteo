const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: '材料出し（zumen-pickup）',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));

  const menu = Menu.buildFromTemplate([
    {
      label: 'ファイル',
      submenu: [
        {
          label: 'DXFを開く...',
          accelerator: 'CmdOrCtrl+O',
          click: () => mainWindow.webContents.send('menu-open-file')
        },
        {
          label: '発注書PDFを印刷...',
          accelerator: 'CmdOrCtrl+P',
          click: () => mainWindow.webContents.send('menu-print')
        },
        { type: 'separator' },
        { label: '終了', role: 'quit' }
      ]
    },
    {
      label: '表示',
      submenu: [
        { label: '全体表示', accelerator: 'CmdOrCtrl+0', click: () => mainWindow.webContents.send('menu-fit') },
        { label: 'ズームイン', accelerator: 'CmdOrCtrl+Plus', click: () => mainWindow.webContents.send('menu-zoom-in') },
        { label: 'ズームアウト', accelerator: 'CmdOrCtrl+Minus', click: () => mainWindow.webContents.send('menu-zoom-out') },
        { type: 'separator' },
        { label: '開発者ツール', accelerator: 'F12', click: () => mainWindow.webContents.openDevTools() }
      ]
    }
  ]);
  Menu.setApplicationMenu(menu);
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// DXFファイルを開くダイアログ
ipcMain.handle('open-dxf-dialog', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'DXFファイルを開く',
    filters: [{ name: 'DXF図面', extensions: ['dxf', 'DXF'] }],
    properties: ['openFile']
  });
  if (result.canceled || !result.filePaths.length) return null;
  const filePath = result.filePaths[0];
  try {
    const content = fs.readFileSync(filePath, { encoding: 'utf8' });
    return { filePath, content };
  } catch (e) {
    // Shift-JIS fallback
    try {
      const buf = fs.readFileSync(filePath);
      return { filePath, content: buf.toString('latin1'), encoding: 'sjis' };
    } catch (e2) {
      return { error: e2.message };
    }
  }
});

// PDFを印刷
ipcMain.handle('print-pdf', async () => {
  mainWindow.webContents.print({ silent: false, printBackground: true });
  return true;
});
