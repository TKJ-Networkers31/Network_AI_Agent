import React from "react";

export class ComponentErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="my-2 p-3 rounded-xl border border-rose-500/20 bg-rose-500/10 text-rose-300 text-xs flex items-center justify-between">
          <div>
            <span className="font-semibold">Komponen Gagal Ditampilkan:</span>{" "}
            <span>{this.state.error?.message || "Terjadi kesalahan internal saat rendering."}</span>
          </div>
          {this.props.onRetry && (
            <button
              type="button"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                this.props.onRetry();
              }}
              className="text-[11px] underline hover:text-white transition ml-2"
            >
              Coba lagi
            </button>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
