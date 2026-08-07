const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');

const API_URL = 'http://127.0.0.1:8000';

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
    const req = http.get(API_URL, (res) => {
      callback(res.statusCode < 500);
    });
    req.on('error', () => setTimeout(check, 500));
    req.setTimeout(1000, () => req.destroy());
  }
  check();
}

function createWindow() {
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
    if (ok) createWindow();
    else {
      createWindow();
      console.warn('Backend not detected. Start it manually with python -m uvicorn src.backend.api:app');
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
