/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{js,jsx}',
    './components/**/*.{js,jsx}',
    './app/**/*.{js,jsx}',
    './src/**/*.{js,jsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "#010079",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#D5AD36",
          foreground: "#010079",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "#D5AD36",
          foreground: "#010079",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        navy: {
          DEFAULT: "#010079",
          50: "#e6e6ff",
          100: "#b3b3ff",
          200: "#8080ff",
          300: "#4d4dff",
          400: "#1a1aff",
          500: "#0000e6",
          600: "#0000b3",
          700: "#010079",
          800: "#000046",
          900: "#000023",
        },
        gold: {
          DEFAULT: "#D5AD36",
          50: "#fdf8e8",
          100: "#f9edc1",
          200: "#f2d06b",
          300: "#e8c34d",
          400: "#D5AD36",
          500: "#b08d2b",
          600: "#8b6f22",
          700: "#665118",
          800: "#41330f",
          900: "#1c1506",
        },
        "background-light": "#F9FAFB",
        "background-paper": "#F5F5F7",
        paper: "#F5F5F7",
        "subtle-bg": "#F9FAFB",
        success: "#059669",
        warning: "#D97706",
        error: "#DC2626",
        info: "#2563EB",
      },
      borderRadius: {
        lg: "0px",
        md: "0px",
        sm: "0px",
        DEFAULT: "0px",
      },
      fontFamily: {
        sans: ["Manrope", "DM Sans", "sans-serif"],
        serif: ["Cormorant Garamond", "serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.5s ease-out forwards",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
