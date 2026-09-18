import { FlatCompat } from '@eslint/eslintrc';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: currentDirectory });

let securityConfig = {};

try {
  const { default: security } = await import('eslint-plugin-security');
  securityConfig = {
    plugins: { security },
    rules: security.configs.recommended.rules,
  };
} catch (error) {
  if (error?.code !== 'ERR_MODULE_NOT_FOUND' || !error.message.includes('eslint-plugin-security')) {
    throw error;
  }

  if (process.env.CI === 'true') {
    throw new Error('В CI обязателен eslint-plugin-security; npm ci не установил плагин.');
  }
}

const config = [
  {
    // Локальные данные и среды не являются исходным JavaScript/TypeScript проекта.
    ignores: ['.next/**', '.venv/**', 'apps/**', 'coverage/**', '/data/**', 'node_modules/**', 'references/**', '.worktrees/**', 'next-env.d.ts'],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    plugins: { 'jsx-a11y': jsxA11y },
    rules: {
      ...jsxA11y.configs.recommended.rules,
      // Существующие компоненты требуют отдельной UI-доработки вне текущего периметра.
      'jsx-a11y/label-has-associated-control': 'off',
      'jsx-a11y/no-noninteractive-element-interactions': 'off',
      'jsx-a11y/no-static-element-interactions': 'off',
    },
  },
  securityConfig,
  {
    // Только эти тесты создают и удаляют изолированные временные Git-репозитории
    // либо обходят заранее известное дерево production-кода; это не runtime-код.
    files: ['scripts/**/*.test.{js,cjs,mjs,ts,tsx}', 'src/productionGraph.test.ts'],
    rules: {
      'security/detect-non-literal-fs-filename': 'off',
    },
  },
];

export default config;
