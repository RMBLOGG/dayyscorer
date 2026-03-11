const CACHE = 'dayyscorer-v3';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  // Hapus semua cache lama
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  // Network-first untuk semua request — selalu ambil versi terbaru
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
