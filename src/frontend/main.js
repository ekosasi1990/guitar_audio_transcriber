const { app, BrowserWindow, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');

const API_URL = 'http://127.0.0.1:8000';

process.on('uncaughtException', (err) => {
  try {
    const logPath = path.join(app.getPath('userData'), 'gat-error.log');
    fs.appendFileSync(logPath, `${new Date().toISOString()} ${err.stack}\n`);
  } catch (_) {
    /* ignore logging failure */
  }
});

function findBackend() {
  const resources = process.resourcesPath;
  const candidates = [
    path.join(resources, 'dist-backend', 'gat-backend', 'gat-backend.exe'),
    path.join(resources, 'dist-backend', 'gat-backend.exe'),
    path.join(__dirname, '..', '..', 'dist-backend', 'gat-backend', 'gat-backend.exe'),
    path.join(__dirname, '..', '..', 'dist-backend', 'gat-backend.exe'),
    path.join(__dirname, '..', 'dist-backend', 'gat-backend', 'gat-backend.exe'),
    path.join(__dirname, '..', 'dist-backend', 'gat-backend.exe'),
    path.join(process.cwd(), 'dist-backend', 'gat-backend', 'gat-backend.exe'),
    path.join(process.cwd(), 'dist-backend', 'gat-backend.exe'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function startBackend() {
  const exe = findBackend();
  if (!exe) return;
  const child = spawn(exe, [], { detached: true });
  child.unref();
}

function waitForBackend(callback) {
  let attempts = 0;
  function check() {
    if (attempts > 30) {
      callback(false);
      return;
    }
    attempts++;
    const req = http.get(`${API_URL}/openapi.json`, (res) => {
      res.resume();
      callback(res.statusCode === 200);
    });
    req.on('error', () => setTimeout(check, 500));
    req.setTimeout(1000, () => req.destroy());
  }
  check();
}

function createWindow() {
  // Grant microphone/camera permission requests (needed for recording).
  session.defaultSession.setPermissionRequestHandler((wc, permission, callback) => {
    callback(permission === 'media' || permission === 'mediaKeySystem');
  });
  session.defaultSession.setPermissionCheckHandler((wc, permission) => {
    return permission === 'media' || permission === 'mediaKeySystem';
  });

  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  win.loadFile(path.join(__dirname, 'index.html'));
}

startBackend();

app.whenReady().then(() => {
  waitForBackend((ok) => {
    if (!ok) {
      console.warn(
        'Backend not detected. Start it manually with python -m uvicorn src.backend.api:app',
      );
    }
    createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
