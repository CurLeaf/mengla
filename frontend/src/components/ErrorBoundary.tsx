import React from "react";

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  State
> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="flex flex-col items-center justify-center h-screen bg-[#050506] text-white">
            <h2 className="text-xl font-bold text-red-500 mb-4">
              页面出现错误
            </h2>
            <p className="text-white/50 mb-6 max-w-md text-center text-sm">
              {this.state.error?.message}
            </p>
            <button
              className="px-5 py-2.5 bg-[#5E6AD2] hover:bg-[#6E7AE2] text-white text-sm font-medium rounded-lg transition-colors"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
            >
              刷新页面
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
