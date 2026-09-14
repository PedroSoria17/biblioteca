(() => {
  const STORAGE_KEY = 'booksApp.config';
  const DEFAULT_CONFIG = { ip: '34.51.73.237:5001', endpoint: '/books-with-images' };
  const PAGE_SIZE = 6;

  const PLACEHOLDER_COVER = `
    <svg viewBox="0 0 24 24" width="64" height="64" fill="currentColor">
      <path d="M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm0 18H6V4h2v14l4-2 4 2V4h2v16z"/>
    </svg>`;

  const state = {
    books: [],
    currentPage: 1
  };

  const els = {
    grid: document.getElementById('cards-grid'),
    pagination: document.getElementById('pagination'),
    prevBtn: document.getElementById('prev-page'),
    nextBtn: document.getElementById('next-page'),
    pageInfo: document.getElementById('page-info'),
    loading: document.getElementById('loading'),
    statusBanner: document.getElementById('status-banner'),
    settingsBtn: document.getElementById('settings-btn'),
    refreshBtn: document.getElementById('refresh-btn'),
    overlay: document.getElementById('settings-overlay'),
    settingsForm: document.getElementById('settings-form'),
    cancelSettings: document.getElementById('cancel-settings'),
    inputIp: document.getElementById('input-ip'),
    inputEndpoint: document.getElementById('input-endpoint')
  };

  function loadConfig() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { ...DEFAULT_CONFIG };
      const parsed = JSON.parse(raw);
      return {
        ip: parsed.ip || DEFAULT_CONFIG.ip,
        endpoint: parsed.endpoint || DEFAULT_CONFIG.endpoint
      };
    } catch (err) {
      return { ...DEFAULT_CONFIG };
    }
  }

  function saveConfig(config) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  }

  function showStatus(message) {
    if (!message) {
      els.statusBanner.hidden = true;
      els.statusBanner.textContent = '';
      return;
    }
    els.statusBanner.hidden = false;
    els.statusBanner.textContent = message;
  }

  function setLoading(isLoading) {
    els.loading.hidden = !isLoading;
    if (isLoading) {
      els.grid.innerHTML = '';
      els.pagination.hidden = true;
    }
  }

  // Busca el primer valor de texto entre varios nombres de etiqueta posibles,
  // ya que distintos microservicios de libros nombran los campos de forma distinta.
  function firstText(node, tagNames) {
    for (const tag of tagNames) {
      const el = node.getElementsByTagName(tag)[0];
      if (el && el.textContent && el.textContent.trim()) {
        return el.textContent.trim();
      }
    }
    return '';
  }

  function firstAttrOrText(node, tagNames, attrNames) {
    for (const tag of tagNames) {
      const el = node.getElementsByTagName(tag)[0];
      if (!el) continue;
      for (const attr of attrNames) {
        const val = el.getAttribute && el.getAttribute(attr);
        if (val && val.trim()) return val.trim();
      }
      if (el.textContent && el.textContent.trim()) return el.textContent.trim();
    }
    return '';
  }

  function extractAuthors(node) {
    // 'autor'/'Autor' es la etiqueta real del microservicio Flask
    // (apps/library_soap_service): <autores><autor>Nombre Apellido</autor></autores>.
    // 'author'/'Author'/'writer' se conservan por compatibilidad con otros
    // microservicios de libros (en inglés).
    const authorTags = ['autor', 'Autor', 'author', 'Author', 'writer', 'Writer'];
    const names = [];
    for (const tag of authorTags) {
      const elements = node.getElementsByTagName(tag);
      for (const el of elements) {
        if (el.textContent && el.textContent.trim()) names.push(el.textContent.trim());
      }
      if (names.length) break;
    }
    if (names.length) return names.join(', ');

    const fallback = firstText(node, ['autores', 'Autores', 'authors', 'Authors']);
    return fallback;
  }

  function extractPrice(node) {
    const raw = firstAttrOrText(
      node,
      ['precio', 'Precio', 'price', 'Price', 'cost', 'Cost'],
      ['value', 'amount']
    );
    if (!raw) return '';
    const numeric = parseFloat(raw.replace(',', '.').replace(/[^0-9.]/g, ''));
    if (Number.isNaN(numeric)) return raw;
    const currencySymbol = /€/.test(raw) ? '€' : '$';
    return `${currencySymbol}${numeric.toFixed(2)}`;
  }

  // Elige la imagen a mostrar en la card: dentro de <images><image>...</image></images>
  // (estructura real de apps/library_soap_service), prefiere la marcada
  // isCover=true; si ninguna lo está, la de menor <order>/<orden>; si no hay
  // ese contenedor, cae a una única etiqueta de imagen suelta (compatibilidad
  // con otros microservicios).
  function extractImageUrl(node) {
    const imagesContainer = node.getElementsByTagName('images')[0]
      || node.getElementsByTagName('Images')[0];

    if (imagesContainer) {
      const imageEls = Array.from(imagesContainer.children).filter(
        (el) => el.tagName === 'image' || el.tagName === 'Image'
      );

      if (imageEls.length) {
        const isCover = (el) => {
          const val = firstText(el, ['isCover', 'iscover', 'es_portada']).toLowerCase();
          return val === 'true' || val === '1';
        };
        const orderOf = (el) => {
          const val = firstText(el, ['order', 'orden']);
          const num = parseInt(val, 10);
          return Number.isNaN(num) ? Number.MAX_SAFE_INTEGER : num;
        };

        const chosen = imageEls.find(isCover)
          || [...imageEls].sort((a, b) => orderOf(a) - orderOf(b))[0];

        return firstAttrOrText(chosen, ['url', 'Url', 'URL'], ['src', 'href']);
      }
    }

    return firstAttrOrText(
      node,
      ['image', 'Image', 'photo', 'Photo', 'cover', 'Cover', 'thumbnail', 'img'],
      ['src', 'url', 'href']
    );
  }

  function parseXmlToBooks(xmlText, imageBaseUrl) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlText, 'application/xml');

    const parserError = doc.getElementsByTagName('parsererror')[0];
    if (parserError) {
      throw new Error('La respuesta del servicio no es un XML válido.');
    }

    const candidateTags = ['book', 'Book', 'item', 'Item', 'entry', 'Entry'];
    let nodes = [];
    for (const tag of candidateTags) {
      const found = doc.getElementsByTagName(tag);
      if (found.length) {
        nodes = Array.from(found);
        break;
      }
    }

    return nodes.map((node, index) => ({
      id: firstText(node, ['id', 'Id', 'ID', 'isbn', 'ISBN']) || String(index),
      title: firstText(node, ['titulo', 'Titulo', 'title', 'Title', 'name', 'Name']) || 'Título no disponible',
      authors: extractAuthors(node) || 'Autor desconocido',
      year: firstText(node, ['anio_publicacion', 'anioPublicacion', 'year', 'Year']),
      isbn: firstText(node, ['isbn', 'ISBN', 'isbn13', 'isbn10']) || 'N/D',
      price: extractPrice(node) || 'N/D',
      image: resolveImageUrl(extractImageUrl(node), imageBaseUrl)
    }));
  }

  // El XML puede traer una URL absoluta (http(s)://...) o relativa
  // (ej. "/uploads/libros/archivo.jpg", tal como la sirve
  // apps/library_soap_service). Una URL relativa nunca debe resolverse
  // contra file:// (el origen del renderer de Electron): se reconstruye
  // contra el mismo host:puerto que realmente respondió la petición XML.
  function resolveImageUrl(url, baseUrl) {
    if (!url) return '';
    if (/^https?:\/\//i.test(url)) return url;
    if (!baseUrl) return url;

    const path = url.startsWith('/') ? url : `/${url}`;
    return `${baseUrl.replace(/\/$/, '')}${path}`;
  }

  function renderCard(book) {
    const card = document.createElement('article');
    card.className = 'book-card';

    const cover = document.createElement('div');
    cover.className = 'book-card__cover';
    if (book.image) {
      const img = document.createElement('img');
      img.src = book.image;
      img.alt = book.title;
      img.loading = 'lazy';
      img.onerror = () => {
        cover.innerHTML = PLACEHOLDER_COVER;
      };
      cover.appendChild(img);
    } else {
      cover.innerHTML = PLACEHOLDER_COVER;
    }

    const body = document.createElement('div');
    body.className = 'book-card__body';
    body.innerHTML = `
      <h3 class="book-card__title" title="${escapeHtml(book.title)}">${escapeHtml(book.title)}</h3>
      <p class="book-card__authors" title="${escapeHtml(book.authors)}">${escapeHtml(book.authors)}</p>
      <p class="book-card__isbn">Año: ${escapeHtml(book.year || 'N/D')}</p>
      <p class="book-card__isbn">ISBN: ${escapeHtml(book.isbn)}</p>
      <div class="book-card__footer">
        <span class="book-card__price">${escapeHtml(book.price)}</span>
      </div>
    `;

    card.appendChild(cover);
    card.appendChild(body);
    return card;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function renderPage() {
    const totalPages = Math.max(1, Math.ceil(state.books.length / PAGE_SIZE));
    state.currentPage = Math.min(Math.max(1, state.currentPage), totalPages);

    els.grid.innerHTML = '';

    if (!state.books.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'No se encontraron libros en la respuesta del microservicio.';
      els.grid.appendChild(empty);
      els.pagination.hidden = true;
      return;
    }

    const start = (state.currentPage - 1) * PAGE_SIZE;
    const pageItems = state.books.slice(start, start + PAGE_SIZE);
    const fragment = document.createDocumentFragment();
    pageItems.forEach((book) => fragment.appendChild(renderCard(book)));
    els.grid.appendChild(fragment);

    els.pagination.hidden = totalPages <= 1;
    els.pageInfo.textContent = `Página ${state.currentPage} de ${totalPages}`;
    els.prevBtn.disabled = state.currentPage <= 1;
    els.nextBtn.disabled = state.currentPage >= totalPages;
  }

  async function loadBooks() {
    const config = loadConfig();
    setLoading(true);
    showStatus('');

    const result = await window.booksApi.fetchBooksXml(config);

    if (!result.ok) {
      setLoading(false);
      state.books = [];
      renderPage();
      showStatus(
        `No se pudo obtener el catálogo desde ${result.url || `${config.ip}${config.endpoint}`}. ` +
        `Detalle: ${result.error}. Verifica la IP y el endpoint en Configuración.`
      );
      return;
    }

    try {
      let imageBaseUrl = '';
      try {
        imageBaseUrl = new URL(result.url).origin;
      } catch (err) {
        imageBaseUrl = '';
      }

      state.books = parseXmlToBooks(result.xml, imageBaseUrl);
      state.currentPage = 1;
    } catch (err) {
      state.books = [];
      showStatus(`Error al interpretar el XML recibido: ${err.message}`);
    } finally {
      setLoading(false);
      renderPage();
    }
  }

  function openSettings() {
    const config = loadConfig();
    els.inputIp.value = config.ip;
    els.inputEndpoint.value = config.endpoint;
    els.overlay.hidden = false;
    els.inputIp.focus();
  }

  function closeSettings() {
    els.overlay.hidden = true;
  }

  els.settingsBtn.addEventListener('click', openSettings);
  els.cancelSettings.addEventListener('click', closeSettings);
  els.overlay.addEventListener('click', (event) => {
    if (event.target === els.overlay) closeSettings();
  });

  els.settingsForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const ip = els.inputIp.value.trim();
    const endpoint = els.inputEndpoint.value.trim();
    if (!ip || !endpoint) return;

    saveConfig({ ip, endpoint });
    closeSettings();
    loadBooks();
  });

  els.refreshBtn.addEventListener('click', loadBooks);

  els.prevBtn.addEventListener('click', () => {
    state.currentPage -= 1;
    renderPage();
  });

  els.nextBtn.addEventListener('click', () => {
    state.currentPage += 1;
    renderPage();
  });

  // Inicializa la configuración por defecto en localStorage si no existe.
  if (!localStorage.getItem(STORAGE_KEY)) {
    saveConfig(DEFAULT_CONFIG);
  }

  loadBooks();
})();
