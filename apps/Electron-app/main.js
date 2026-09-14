const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const http = require('http');
const https = require('https');

const REQUEST_TIMEOUT_MS = 10000;

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 720,
    minHeight: 560,
    backgroundColor: '#f2f2f7',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  win.loadFile(path.join(__dirname, 'index.html'));
}

// Descarga el XML del microservicio de libros desde el proceso principal
// para evitar restricciones de CORS al hacer la peticion desde el renderer.
function fetchXml(targetUrl) {
  return new Promise((resolve, reject) => {
    let parsed;
    try {
      parsed = new URL(targetUrl);
    } catch (err) {
      reject(new Error('URL invalida: ' + targetUrl));
      return;
    }

    const client = parsed.protocol === 'https:' ? https : http;

    const req = client.get(
      parsed,
      {
        headers: { Accept: 'application/xml, text/xml' },
        timeout: REQUEST_TIMEOUT_MS
      },
      (res) => {
        if (res.statusCode && (res.statusCode < 200 || res.statusCode >= 300)) {
          res.resume();
          reject(new Error(`El servicio respondio con codigo HTTP ${res.statusCode}`));
          return;
        }

        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          data += chunk;
        });
        res.on('end', () => resolve(data));
      }
    );

    req.on('timeout', () => {
      req.destroy(new Error('Tiempo de espera agotado al conectar con el microservicio'));
    });

    req.on('error', (err) => reject(err));
  });
}

ipcMain.handle('fetch-books-xml', async (_event, { ip, endpoint }) => {
  const cleanIp = String(ip || '').trim();
  let cleanEndpoint = String(endpoint || '').trim();

  if (!cleanIp) {
    return { ok: false, error: 'Debes indicar la IP del microservicio.' };
  }
  if (!cleanEndpoint.startsWith('/')) {
    cleanEndpoint = '/' + cleanEndpoint;
  }

  const hasScheme = /^https?:\/\//i.test(cleanIp);
  const base = hasScheme ? cleanIp.replace(/\/$/, '') : `http://${cleanIp}`;
  const url = `${base}${cleanEndpoint}`;

  try {
    const xml = await fetchXml(url);
    return { ok: true, xml, url };
  } catch (err) {
    return { ok: false, error: err.message || String(err), url };
  }
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
