/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#6366f1',
          'primary-hover': '#4f46e5',
          'primary-light': '#eef2ff',
        },
        neutral: {
          bg: '#0f172a',
          surface: '#1e293b',
          border: '#334155',
        },
      },
    },
  },
  plugins: [],
}
