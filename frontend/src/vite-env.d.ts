/// <reference types="vite/client" />

declare module 'jest-axe' {
  import type { AxeResults } from 'axe-core';

  export function axe(
    container: Element | string,
    options?: Record<string, unknown>,
  ): Promise<AxeResults>;

  export const toHaveNoViolations: {
    toHaveNoViolations(results: AxeResults): { pass: boolean; message(): string };
  };

  export function configureAxe(
    options?: Record<string, unknown>,
  ): typeof axe;
}

interface CustomMatchers<R = unknown> {
  toHaveNoViolations(): R;
}

declare module 'vitest' {
  interface Assertion<T> extends CustomMatchers<T> {}
  interface AsymmetricMatchersContaining extends CustomMatchers {}
}
