// frontend/src/plugins/vuetify.js (veya main.js içinde createVuetify kısmı)

import 'vuetify/styles';
import { createVuetify } from 'vuetify';
import * as components from 'vuetify/components';
import * as directives from 'vuetify/directives';
import '@mdi/font/css/materialdesignicons.css'; // MDI ikonları için

// Açık Tema Renkleri
const myCustomLightTheme = {
  dark: false, // Bu bir açık tema
  colors: {
    primary: '#1E88E5',    // Blue600
    secondary: '#424242',  // Grey800
    accent: '#FFC107',     // Amber
    error: '#D32F2F',      // Red700
    info: '#0288D1',       // LightBlue700
    success: '#388E3C',    // Green700
    warning: '#FFA000',    // Amber700
    background: '#F5F5F5', // Grey100
    surface: '#FFFFFF',     // White
  }
};

// Koyu Tema Renkleri
const myCustomDarkTheme = {
  dark: true, // Bu bir koyu tema
  colors: {
    primary: '#90CAF9',    // Blue200
    secondary: '#BDBDBD',  // Grey400
    accent: '#FFD54F',     // Amber300
    error: '#EF9A9A',      // Red200
    info: '#81D4FA',       // LightBlue200
    success: '#A5D6A7',    // Green200
    warning: '#FFE082',    // Amber200
    background: '#121212', // Klasik koyu arka plan
    surface: '#1E1E1E',     // Kartlar vb. için
  }
};

const vuetify = createVuetify({
  components,
  directives,
  icons: {
    defaultSet: 'mdi',
  },
  theme: {
    defaultTheme: 'myCustomDarkTheme', // Mevcut koyu temanızı koruyoruz veya 'myCustomLightTheme' yapabilirsiniz
    themes: {
      myCustomLightTheme, // Tanımladığımız açık tema
      myCustomDarkTheme,  // Tanımladığımız koyu tema
      // Vuetify'nin varsayılan 'light' ve 'dark' temalarını da burada bırakabilir veya kaldırabilirsiniz
      // light: { ...varsayılan light tema renkleri... },
      // dark: { ...varsayılan dark tema renkleri... },
    },
  },
});

export default vuetify; // Eğer ayrı bir plugins/vuetify.js dosyası ise
// Eğer main.js içindeyse: app.use(vuetify);