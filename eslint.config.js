import globals from "globals";

import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";

import importPlugin from "eslint-plugin-import";
import eslintConfigPrettier from "eslint-config-prettier/flat";
import eslintConfigs from "@dr.pogodin/eslint-configs";

import babelEslintParser from "@babel/eslint-parser";

export default defineConfig([
  // run on all js and jsx files in the static directory and subdirectories
  { files: ["**/*.js", "**/*.jsx"] },
  globalIgnores([
    "**/node_modules",
    "baselayer",
    "static/build",
    "eslint.config.js",
    "rspack.config.js",
    "doc",
  ]),
  {
    languageOptions: {
      parser: babelEslintParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          presets: ["@babel/preset-env", "@babel/preset-react"],
        },
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: {
        ...globals.browser,
      },
    },
  },
  js.configs.recommended,
  importPlugin.flatConfigs.recommended,
  eslintConfigs.configs.javascript,
  eslintConfigs.configs.react,
  {
    rules: {
      "@babel/new-cap": "off",
      camelcase: "off",
      "default-param-last": "off", // otherwise complains for all reducers
      "jsx-a11y/click-events-have-key-events": "off",
      "jsx-a11y/label-has-associated-control": "off",
      "jsx-a11y/control-has-associated-label": "off",
      "no-param-reassign": "off",
      "no-unused-vars": "off",
      "no-unsafe-optional-chaining": "off",
      "no-useless-escape": "off",
      "no-constant-binary-expression": "warn",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react/jsx-wrap-multilines": "off",
      "react/jsx-one-expression-per-line": "off",
      "react/jsx-props-no-spreading": "off",
      "react/jsx-curly-newline": "off",
      "sort-keys": "off",
    },
  },
  {
    settings: {
      "import/resolver": {
        webpack: {
          config: "rspack.config.js",
        },
      },
      react: {
        version: "detect",
      },
    },
  },
  eslintConfigPrettier,
]);
