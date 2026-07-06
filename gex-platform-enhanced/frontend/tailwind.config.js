/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",  // toggle with <html class="dark">
  theme: {
    extend: {
      fontFamily: {
        display: ['"Inria Sans"', 'system-ui', 'sans-serif'],
        sans:    ['"Inria Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono:    ['"JetBrains Mono"', '"Fira Code"', '"Cascadia Code"', 'monospace'],
      },

      colors: {
        neutral: {
          canvas:       '#f8fafc',
          surface:      '#ffffff',
          surfaceMuted: '#f1f5f9',
          hover:        '#e2e8f0',
          border:       '#cbd5e1',
          borderStrong: '#94a3b8',
          text:         '#0f172a',
          subtle:       '#334155',
          muted:        '#64748b',
          inverse:      '#ffffff',
        },
        brand: {
          DEFAULT: '#0f766e',
          50:  '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#0f766e',
          600: '#0f766e',
          700: '#115e59',
          800: '#134e4a',
          900: '#0f3f3b',
          hover:   '#115e59',
          active:  '#134e4a',
          light:   '#ccfbf1',
          border:  '#5eead4',
          text:    '#115e59',
          focus:   'rgba(15, 118, 110, 0.22)',
        },
        status: {
          blocker: {
            DEFAULT: '#b91c1c',
            hover:   '#991b1b',
            light:   '#fee2e2',
            border:  '#fecaca',
            text:    '#7f1d1d',
          },
          warning: {
            DEFAULT: '#b45309',
            hover:   '#92400e',
            light:   '#fef3c7',
            border:  '#fde68a',
            text:    '#78350f',
          },
          success: {
            DEFAULT: '#15803d',
            hover:   '#166534',
            light:   '#dcfce7',
            border:  '#bbf7d0',
            text:    '#14532d',
          },
        },
      },

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

      spacing: {
        sidebar: '72px',
        header:  '56px',
      },

      borderRadius: {
        DEFAULT: '0.5rem',
        sm: '0.375rem',
        md: '0.5rem',
        lg: '0.5rem',
        xl: '0.5rem',
        '2xl': '0.5rem',
      },

      boxShadow: {
        panel:    '0 1px 2px rgba(15, 23, 42, 0.04)',
        dropdown: '0 8px 24px rgba(15, 23, 42, 0.12)',
        focus:    '0 0 0 3px rgba(15, 118, 110, 0.22)',
      },

      letterSpacing: {
        caps:   '0.08em',
        widest: '0.14em',
      },

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
