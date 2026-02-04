/**
 * Fallback when @types/react is missing. Install: pnpm add -D @types/react @types/react-dom
 */
declare module "react" {
  export interface ChangeEvent<T = HTMLElement> {
    target: EventTarget & T;
  }
  export const useState: <S>(initial: S | (() => S)) => [S, (s: S | ((prev: S) => S)) => void];
  export const useEffect: (effect: () => void | (() => void), deps?: unknown[]) => void;
  export const useMemo: <T>(factory: () => T, deps: unknown[]) => T;
  export const StrictMode: unknown;
  export default unknown;
}

declare module "react/jsx-runtime" {
  export const jsx: (type: unknown, props: unknown, key?: string) => unknown;
  export const jsxs: (type: unknown, props: unknown, key?: string) => unknown;
  export const Fragment: unknown;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: Record<string, unknown>;
  }
}
