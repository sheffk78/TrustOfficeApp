// ESLint 9 flat config for TrustOffice frontend.
// Purpose: catch module-scope ReferenceErrors (e.g. an unimported lucide icon
// used in a nav array) at lint time instead of shipping a blank screen.
// The 2026-08-11 incident: MobileBottomNav used BarChart3 without importing it —
// a load-time ReferenceError that killed the whole React app. `no-undef` catches it.
const js = require('@eslint/js');
const react = require('eslint-plugin-react');
const reactHooks = require('eslint-plugin-react-hooks');

module.exports = [
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    plugins: {
      react,
      'react-hooks': reactHooks,
    },
    linterOptions: {
      reportUnusedDisableDirectives: 'off',
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: 2022,
        sourceType: 'module',
      },
      globals: {
        // Browser globals
        window: 'readonly',
        document: 'readonly',
        navigator: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        location: 'readonly',
        fetch: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        Blob: 'readonly',
        File: 'readonly',
        FormData: 'readonly',
        Headers: 'readonly',
        Response: 'readonly',
        confirm: 'readonly',
        XMLHttpRequest: 'readonly',
        Notification: 'readonly',
        atob: 'readonly',
        btoa: 'readonly',
        TextDecoder: 'readonly',
        FileReader: 'readonly',
        AbortController: 'readonly',
        IntersectionObserver: 'readonly',
        ResizeObserver: 'readonly',
        MutationObserver: 'readonly',
        CustomEvent: 'readonly',
        Event: 'readonly',
        KeyboardEvent: 'readonly',
        MouseEvent: 'readonly',
        // Node/test globals
        process: 'readonly',
        module: 'readonly',
        require: 'readonly',
        __dirname: 'readonly',
        global: 'readonly',
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        jest: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
    rules: {
      // THE gate: any use of an undefined identifier fails lint.
      'no-undef': 'error',
      // Keep it focused — don't introduce a wall of style rules that
      // would make the existing codebase fail lint on unrelated noise.
      'no-unused-vars': 'off',
      'react/prop-types': 'off',
      'react/react-in-jsx-scope': 'off',
      'no-empty': 'off',
      'no-useless-escape': 'off',
      // react-hooks exhaustive-deps fires many warnings (and unused-disable
      // directives) across the codebase. It's not the bug class this gate
      // guards (undefined identifiers) — disable to keep the gate green.
      'react-hooks/exhaustive-deps': 'off',
    },
    settings: {
      react: { version: 'detect' },
    },
  },
  {
    // Ignore build output and deps
    ignores: ['build/**', 'node_modules/**', 'public/**', 'coverage/**'],
  },
];
