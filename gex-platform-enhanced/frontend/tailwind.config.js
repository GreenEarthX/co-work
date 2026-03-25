/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",  // toggle with <html class="dark">
  theme: {
    extend: {
      // ── Font families ──────────────────────────────────────────────────────
      fontFamily: {
        // Headings / display — matched to Lovable design system
        display: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        // Body copy
        sans:    ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        // Numbers, scores, metrics, code
        mono:    ['"JetBrains Mono"', '"Fira Code"', '"Cascadia Code"', 'monospace'],
      },

      // ── Brand palette ──────────────────────────────────────────────────────
      colors: {
        brand: {
          50:  '#f0fdf9',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#0ea5a0',  // PRIMARY — buttons, active states, accents
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          DEFAULT: '#0ea5a0',
        },
        // Neutral surfaces — light mode
        surface: {
          bg:     '#f5f6f8',
          card:   '#ffffff',
          border: '#e2e8f0',
          hover:  '#f8fafc',
          muted:  '#f1f5f9',
        },
        // Semantic
        success: '#16a34a',
        warning: '#d97706',
        danger:  '#dc2626',
        info:    '#0ea5e9',

        // Rating letter colours (used in badge contexts)
        rating: {
          investment: '#16a34a',  // AAA / AA / A
          crossover:  '#d97706',  // BBB / BB
          speculative:'#dc2626',  // B and below
        },
      },

      // ── Typography scale (compact, data-dense) ─────────────────────────────
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],   // 10px
        xs:    ['0.6875rem', { lineHeight: '1rem' }],       // 11px
        sm:    ['0.8125rem', { lineHeight: '1.25rem' }],    // 13px
        base:  ['0.875rem',  { lineHeight: '1.375rem' }],   // 14px
        lg:    ['1rem',      { lineHeight: '1.5rem' }],     // 16px
        xl:    ['1.125rem',  { lineHeight: '1.625rem' }],   // 18px
        '2xl': ['1.25rem',   { lineHeight: '1.75rem' }],    // 20px
        '3xl': ['1.5rem',    { lineHeight: '2rem' }],       // 24px
        '4xl': ['2rem',      { lineHeight: '2.5rem' }],     // 32px
      },

      // ── Layout constants ────────────────────────────────────────────────────
      spacing: {
        sidebar: '72px',
        header:  '56px',
      },

      // ── Border radius ───────────────────────────────────────────────────────
      borderRadius: {
        DEFAULT: '6px',
        md:  '8px',
        lg:  '10px',
        xl:  '14px',
        '2xl': '18px',
      },

      // ── Shadows ─────────────────────────────────────────────────────────────
      boxShadow: {
        card:     '0 1px 3px 0 rgba(0,0,0,0.07), 0 1px 2px -1px rgba(0,0,0,0.05)',
        'card-md':'0 4px 12px 0 rgba(0,0,0,0.08)',
        dropdown: '0 4px 16px 0 rgba(0,0,0,0.12)',
        ring:     '0 0 0 3px rgba(14,165,160,0.18)',
      },

      // ── Letter spacing ──────────────────────────────────────────────────────
      letterSpacing: {
        caps:   '0.08em',
        widest: '0.14em',
      },

      // ── Keyframes / animations ──────────────────────────────────────────────
      keyframes: {
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          from: { opacity: '0', transform: 'translateX(-8px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-4px)' },
          '20%, 40%, 60%, 80%': { transform: 'translateX(4px)' },
        },
      },
      animation: {
        'fade-in':  'fadeIn 0.2s ease',
        'slide-in': 'slideIn 0.18s ease',
        'shake':    'shake 0.5s ease-in-out',
      },
    },
  },
  plugins: [],
}
