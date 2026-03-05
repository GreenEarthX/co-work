/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        // GEX Brand — teal extracted from staging site
        brand: {
          50:  '#f0fdf9',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#0ea5a0',   // PRIMARY — buttons, active states, accents
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          DEFAULT: '#0ea5a0',
        },
        // Neutral surface palette
        surface: {
          bg:     '#f5f6f8',  // page background
          card:   '#ffffff',  // card/panel
          border: '#e2e8f0',  // dividers
          hover:  '#f8fafc',  // row hover
          muted:  '#f1f5f9',  // table header bg
        },
        // Semantic
        success: '#16a34a',
        warning: '#d97706',
        danger:  '#dc2626',
        info:    '#0ea5e9',
      },
      fontSize: {
        '2xs': ['0.65rem', { lineHeight: '1rem' }],
        xs:    ['0.75rem', { lineHeight: '1.125rem' }],
        sm:    ['0.8125rem', { lineHeight: '1.25rem' }],
        base:  ['0.875rem', { lineHeight: '1.375rem' }],
        lg:    ['1rem',     { lineHeight: '1.5rem' }],
        xl:    ['1.125rem', { lineHeight: '1.625rem' }],
      },
      spacing: {
        sidebar: '72px',   // icon-only sidebar width
        header:  '56px',   // top bar height
      },
      borderRadius: {
        DEFAULT: '6px',
        lg: '8px',
        xl: '12px',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,0.08), 0 1px 2px -1px rgba(0,0,0,0.06)',
        dropdown: '0 4px 16px 0 rgba(0,0,0,0.12)',
      },
      letterSpacing: {
        widest: '0.12em',
      },
    },
  },
  plugins: [],
}
