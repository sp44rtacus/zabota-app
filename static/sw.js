self.addEventListener('install', (e) => {
    console.log('[Service Worker] Установлен. Приложение готово к работе!');
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    console.log('[Service Worker] Активирован.');
});

// Перехватываем запросы (здесь можно настроить оффлайн-режим)
self.addEventListener('fetch', (e) => {
    e.respondWith(fetch(e.request));
});