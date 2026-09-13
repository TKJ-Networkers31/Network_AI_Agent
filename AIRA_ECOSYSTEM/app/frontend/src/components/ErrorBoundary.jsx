import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Keep this visible in the browser console for debugging - this is
    // the ONLY place a runtime error should ever be swallowed silently
    // instead of blanking the whole app.
    console.error("AIRA UI crashed:", error, info?.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center gap-4 bg-app text-white px-6 text-center">
        <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center text-2xl">
          ⚠️
        </div>
        <h1 className="text-lg font-semibold">Terjadi kesalahan pada tampilan</h1>
        <p className="text-sm text-white/50 max-w-sm">
          AIRA mengalami error yang tidak terduga di sisi frontend. Backend tetap berjalan normal.
          Coba muat ulang halaman.
        </p>
        {this.state.error?.message && (
          <pre className="text-[11px] text-red-300/80 bg-black/30 border border-red-500/20 rounded-lg px-3 py-2 max-w-md overflow-x-auto text-left">
            {this.state.error.message}
          </pre>
        )}
        <button
          onClick={this.handleReload}
          className="mt-2 bg-accent-gradient text-white text-sm font-semibold px-4 py-2 rounded-lg"
        >
          Muat Ulang
        </button>
      </div>
    );
  }
}