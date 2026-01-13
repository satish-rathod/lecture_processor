/** @type {import('tailwindcss').Config} */
export default {
    darkMode: 'class',
    content: [
        './index.html',
        './src/**/*.{js,ts,jsx,tsx}',
    ],
    theme: {
        extend: {
            colors: {
                // Notion-inspired dark mode palette
                background: '#191919',
                foreground: '#ebebeb',

                muted: {
                    DEFAULT: '#252525',
                    foreground: '#9b9b9b',
                },

                accent: {
                    DEFAULT: '#2f2f2f',
                    foreground: '#ebebeb',
                },

                primary: {
                    DEFAULT: '#447acb',
                    foreground: '#ffffff',
                },

                secondary: {
                    DEFAULT: '#363636',
                    foreground: '#ebebeb',
                },

                destructive: {
                    DEFAULT: '#be524b',
                    foreground: '#ffffff',
                },

                success: {
                    DEFAULT: '#4f9768',
                    foreground: '#ffffff',
                },

                warning: {
                    DEFAULT: '#cb7b37',
                    foreground: '#ffffff',
                },

                border: 'rgba(255, 255, 255, 0.08)',
                input: 'rgba(255, 255, 255, 0.08)',
                ring: '#447acb',
            },

            fontFamily: {
                sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
            },

            borderRadius: {
                lg: '8px',
                md: '6px',
                sm: '4px',
            },
        },
    },
    plugins: [],
}
