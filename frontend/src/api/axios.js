// frontend/src/api/axios.js (NİHAİ ve DOĞRU HALİ)

import axios from 'axios';

const apiClient = axios.create({
  // baseURL'i ayarlayarak tüm göreceli isteklerin doğru ana adrese gitmesini sağlıyoruz.
  // Bu satır, localhost'a yapılan istekleri düzeltecektir.
  baseURL: '/',
  headers: {
    'Content-Type': 'application/json',
  }
});

// Not: Interceptor'larınızı buraya ekleyebilirsiniz veya main.js'de bırakabilirsiniz.
// Kod tutarlılığı için onları main.js'de bırakmak daha iyidir.

export default apiClient;
