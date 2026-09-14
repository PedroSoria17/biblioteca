const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('booksApi', {
  fetchBooksXml: (config) => ipcRenderer.invoke('fetch-books-xml', config)
});
