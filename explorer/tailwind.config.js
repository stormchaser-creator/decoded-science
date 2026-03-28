/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          base: '#0a0a0f',
          raised: '#0d0d18',
          card: '#12121e',
          border: '#1e1e2e',
        },
        accent: {
          DEFAULT: '#7c6af7',
          hover: '#9580ff',
          muted: '#9991d0',
        },
      },
    },
  },
  plugins: [],
}
