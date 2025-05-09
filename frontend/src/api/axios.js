// frontend/src/api/axios.js
import axios from 'axios';

// Temel URL'leri burada tanımlayabiliriz veya boş bırakabiliriz
// const API_BASE_URL = 'http://localhost:8000'; // Örnek

const apiClient = axios.create({
  // baseURL: API_BASE_URL, // Eğer tüm istekler aynı base URL'e gidecekse
  headers: {
    'Content-Type': 'application/json', // Varsayılan olarak JSON bekleyelim
    // Diğer genel başlıklar buraya eklenebilir
  }
});

// Yapılandırılmış instance'ı export et
export default apiClient;