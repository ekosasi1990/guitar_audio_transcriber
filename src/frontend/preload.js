const { contextBridge } = require('electron');

const API_URL = 'http://127.0.0.1:8000';

contextBridge.exposeInMainWorld('gtrApi', {
  url: API_URL,
});
