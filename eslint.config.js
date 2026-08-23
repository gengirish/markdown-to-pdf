import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Anchored with ** because this config sits at the repo root while the build
  // output lives in the workspaces. A bare 'dist' resolves relative to this
  // file, so it ignored <root>/dist — which does not exist — and left eslint
  // linting apps/legacy-web/dist's minified bundles: 111 errors, none real.
  globalIgnores([
    '**/dist/**',
    '**/build/**',
    '**/.next/**',
    '**/node_modules/**',
    '**/coverage/**',
    '**/playwright-report/**',
    '**/test-results/**',
  ]),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
    },
  },
])
